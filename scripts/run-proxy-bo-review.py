#!/usr/bin/env python3
"""CECA-BO-Review runner — standalone review artifact, not part of the dissertation.

Copied and adapted from scripts/run-proxy-bo.py (left completely unmodified)
to run alpha/auctions/ceca_bo_review.py's allocation-stability variant on the
same benchmarks, for direct comparison against the original CECA_BO_Proxy.
Logs to data/{benchmark}-logs/log_Proxy-BO-Review_{timestamp}.csv, a distinct
filename prefix from the original "Proxy-BO" so the two never mix in any
existing run registry or analysis script.
"""

import os
import pandas as pd
from datetime import datetime
import argparse
import concurrent.futures

from dotenv import load_dotenv

from alpha.auctions.ceca import CECA_XOR
from alpha.auctions.ceca_bo_review import CECA_BO_Review_Proxy_Factory
from alpha.persons.full_person import FullPerson
from alpha.scenario import scenarios
from alpha.util import setup_logging, token_tracker


def get_scenario_by_code(code):
    for s in scenarios:
        if s.code == code:
            return s
    return None


def discover_scenarios_and_setups(benchmark):
    base_dir = os.path.join("data", benchmark)
    if not os.path.isdir(base_dir):
        print(f"[ERROR] Benchmark directory does not exist: {base_dir}")
        return []
    scenario_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    tasks = []
    for scenario_code in scenario_dirs:
        scenario_path = os.path.join(base_dir, scenario_code)
        for setup_index in os.listdir(scenario_path):
            if os.path.isdir(os.path.join(scenario_path, setup_index)):
                tasks.append((scenario_code, setup_index))
    return tasks


def process_scenario(benchmark, scenario_code, setup_index, proxy_factory, timestamp, max_iterations=None):
    directory = os.path.join("data", benchmark, scenario_code, str(setup_index))
    scenario_obj = get_scenario_by_code(scenario_code)
    if not scenario_obj:
        return None, None

    print(f"[INFO] Processing scenario={scenario_code}, setup={setup_index}")

    try:
        fullperson_files = [f for f in os.listdir(directory) if f.startswith("FullPerson") and f.endswith(".json")]
        if not fullperson_files:
            return None, None

        persons = []
        for fp_file in fullperson_files:
            with open(os.path.join(directory, fp_file)) as f:
                p = FullPerson.from_json(f.read())
                p.demand_mode = "RAND"
                persons.append(p)

        proxies = [proxy_factory(person) for person in persons]
        auction = CECA_XOR(max_iterations=max_iterations)
        allocation = auction(scenario=scenario_obj, agents=proxies, persons=persons)

        values = []
        for proxy_allocation, proxy in zip(allocation, proxies):
            bundle, payment = proxy_allocation
            if bundle.total_quantity() == 0:
                continue
            values.append(proxy.RealPerson().Message("value", {"bundle": bundle}))

        row = {
            "scenario": scenario_code,
            "setup_index": setup_index,
            "auction_values": values,
            "total_auction_value": sum(values),
            "human_interactions": [proxy.NumberOfHumanInteractions() for proxy in proxies],
            "avg_human_interactions": (
                sum(proxy.NumberOfHumanInteractions() for proxy in proxies) / len(proxies) if proxies else 0
            ),
            "stopped_reason": [getattr(proxy, "_stopped_reason", None) for proxy in proxies],
        }

        log_df = pd.DataFrame(auction.log_rows)
        log_df["scenario"] = scenario_code
        log_df["setup_index"] = setup_index
        return row, log_df

    except Exception as e:
        print(f"Error: {e}")
        return None, None


def _init_worker(env_path):
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path, override=True)


def main():
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--env_path",     type=str, default=".env",
                        help="Provider for the FullPerson simulated bidder's own LLM calls.")
    parser.add_argument("--benchmark",    type=str, required=True)
    parser.add_argument("--cap",          type=int, required=True)
    parser.add_argument("--seed_size",    type=int, default=6,
                        help="Number of bundles queried upfront to bootstrap the GP.")
    parser.add_argument("--kappa",        type=float, default=2.0,
                        help="Exploration weight in the UCB acquisition function (mean + kappa*std).")
    parser.add_argument("--confidence_stop_ratio", type=float, default=0.1,
                        help="Stop querying once std/|mean| for the best candidate falls below this.")
    parser.add_argument("--stability_window", type=int, default=3,
                        help="Stop once the proxy's own top bundle is unchanged for this many consecutive rounds.")
    parser.add_argument("--max_iterations", type=int, default=None)
    parser.add_argument("--random_seed",  type=int, default=0)
    args = parser.parse_args()

    token_tracker.set_context(benchmark=args.benchmark, stage="PROXY-BO-REVIEW")
    load_dotenv(dotenv_path=args.env_path)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    overall_log_df = pd.DataFrame()
    rows = []

    def make_factory():
        return CECA_BO_Review_Proxy_Factory(
            cap=args.cap,
            seed_size=args.seed_size,
            kappa=args.kappa,
            confidence_stop_ratio=args.confidence_stop_ratio,
            stability_window=args.stability_window,
            random_seed=args.random_seed,
        )

    tasks = discover_scenarios_and_setups(args.benchmark)
    if not tasks:
        print("[WARN] No tasks found.")
        return

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=min(12, len(tasks)),
        initializer=_init_worker, initargs=(args.env_path,)
    ) as executor:
        futures = [
            executor.submit(process_scenario, args.benchmark, sc, si, make_factory(), timestamp, args.max_iterations)
            for sc, si in tasks
        ]
        for future in concurrent.futures.as_completed(futures):
            row, log_df = future.result()
            if row is not None:
                rows.append(row)
                overall_log_df = pd.concat([overall_log_df, log_df], ignore_index=True)

    overall_log_df["Proxy"] = "Proxy-BO-Review"
    overall_log_df["Proxy-seed_size"] = args.seed_size
    overall_log_df["Proxy-kappa"]     = args.kappa
    overall_log_df["Proxy-stability_window"] = args.stability_window
    overall_log_df["Person"]    = "FullPerson"
    overall_log_df["Timestamp"] = timestamp
    from alpha.util import get_llm_model, get_llm_provider
    overall_log_df["Provider"] = get_llm_provider()
    overall_log_df["Model"] = get_llm_model()

    out_dir = f"data/{args.benchmark}-logs"
    os.makedirs(out_dir, exist_ok=True)
    log_filename = os.path.join(out_dir, f"log_Proxy-BO-Review_{timestamp}.csv")
    overall_log_df.to_csv(log_filename, index=False)
    print(f"[INFO] Saved to {log_filename}")

    for r in rows:
        print(f"  Setup {r['setup_index']}: welfare={r['total_auction_value']}  interactions={r['human_interactions']}  stopped_reason={r['stopped_reason']}")


if __name__ == "__main__":
    main()
