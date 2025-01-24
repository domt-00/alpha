#!/usr/bin/env python3

import os
import pandas as pd
from datetime import datetime
import argparse
import concurrent.futures

from dotenv import load_dotenv

from alpha.auctions.ceca import CECA_XOR
from alpha.auctions.ceca_purellm_g import CECA_PureLLM_G_Proxy_Factory
from alpha.persons.full_person import FullPerson
from alpha.scenario import scenarios
from alpha.util import setup_logging


def get_scenario_by_code(code):
    """Return the scenario object (from alpha.scenario) matching the given code."""
    for s in scenarios:
        if s.code == code:
            return s
    return None


def discover_scenarios_and_setups(benchmark):
    """
    Discover which scenarios (directories) and setup subdirectories exist under data/<benchmark>.

    Returns:
        A list of tuples: [(scenario_code, setup_subdir), ... ]
    """
    base_dir = os.path.join("data", benchmark)
    if not os.path.isdir(base_dir):
        print(f"[ERROR] Benchmark directory does not exist: {base_dir}")
        return []

    scenario_dirs = [
        d for d in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, d))
    ]

    tasks = []
    for scenario_code in scenario_dirs:
        scenario_path = os.path.join(base_dir, scenario_code)
        setup_subdirs = [
            s for s in os.listdir(scenario_path)
            if os.path.isdir(os.path.join(scenario_path, s))
        ]
        for setup_index in setup_subdirs:
            tasks.append((scenario_code, setup_index))

    return tasks


def process_scenario(benchmark, scenario_code, setup_index, proxy_factory, timestamp):
    """
    Worker function to process a single scenario + setup combination with CECA_PureLLM_G_Proxy.

    Args:
        benchmark (str): The benchmark name (e.g. 'round3').
        scenario_code (str): The code of the scenario directory.
        setup_index (str): The setup folder name (e.g. '0', '1', '2', ...).
        proxy_factory: The CECA_PureLLM_G_Proxy_Factory instance.
        timestamp (str): The timestamp string for output file labeling.

    Returns:
        tuple: (row, log_df)
          - row is a dict summarizing results for this scenario+setup
          - log_df is a pandas DataFrame containing the auction logs
    """
    directory = os.path.join("data", benchmark, scenario_code, str(setup_index))
    scenario_obj = get_scenario_by_code(scenario_code)

    if not scenario_obj:
        print(f"[WARN] No scenario object found for code={scenario_code}. Skipping.")
        return None, None

    print(f"[INFO] Processing scenario={scenario_code}, setup={setup_index} from {directory}")

    try:
        # Gather FullPerson files
        fullperson_files = [
            f for f in os.listdir(directory)
            if f.startswith("FullPerson") and f.endswith(".json")
        ]
        if not fullperson_files:
            print(f"[WARN] No FullPerson JSON files found in {directory}. Skipping.")
            return None, None

        persons = []

        # Read each FullPerson JSON
        for fp_file in fullperson_files:
            full_fp_path = os.path.join(directory, fp_file)

            with open(full_fp_path, "r") as f:
                p = FullPerson.from_json(f.read())
                # You can set demand_mode if needed; e.g. "RAND"
                p.demand_mode = "RAND"
                persons.append(p)

        # Create proxies for each person
        proxies = [proxy_factory(person) for person in persons]

        # Initialize and run the auction
        auction = CECA_XOR()
        print(f"[INFO] Running auction for scenario={scenario_code}, setup={setup_index} with {len(persons)} persons.")
        allocation = auction(scenario=scenario_obj, agents=proxies, persons=persons)

        # Calculate values based on allocation
        values = []
        for proxy_allocation, proxy in zip(allocation, proxies):
            bundle, payment = proxy_allocation
            if bundle.total_quantity() == 0:
                continue
            value = proxy.RealPerson().Message("value", {"bundle": bundle})
            values.append(value)

        # Summary row
        row = {
            "scenario": scenario_code,
            "setup_index": setup_index,
            "auction_values": values,
            "total_auction_value": sum(values),
            "human_interactions": [proxy.NumberOfHumanInteractions() for proxy in proxies],
            "average_human_interactions": (
                sum([proxy.NumberOfHumanInteractions() for proxy in proxies]) / len(proxies)
                if proxies else 0
            ),
        }

        # Convert auction log to DataFrame
        log_df = pd.DataFrame(auction.log_rows)
        log_df["scenario"] = scenario_code
        log_df["setup_index"] = setup_index

        return row, log_df

    except Exception as e:
        print(f"Error processing scenario={scenario_code}, setup={setup_index}: {e}")
        return None, None


def main():
    setup_logging()

    parser = argparse.ArgumentParser(
        description="Run CECA_PureLLM_G_Proxy Auction Simulation with environment variables."
    )

    # New arguments to match run-proxy-h
    parser.add_argument("--env_path", type=str, default=".env",
                        help="Path to the .env file to load environment variables from.")
    parser.add_argument("--benchmark", type=str, required=True,
                        help="Name of the benchmark (e.g. 'round3').")

    # Additional parameters for PureLLM-G proxy
    parser.add_argument("--cap", type=int, required=True,
                        help="Cap on number of queries.")
    parser.add_argument("--min_iterations", type=int, required=True,
                        help="Minimum number of iterations for the proxy to run.")
    parser.add_argument("--check_priority", type=str, required=True,
                        help="Priority setting for CHECK actions in the proxy.")
    parser.add_argument("--target_bundle_priority", type=str, required=True,
                        help="Priority setting for TARGET_BUNDLE actions in the proxy.")
    parser.add_argument("--happy_priority", type=str, required=True,
                        help="Priority setting for HAPPY actions in the proxy.")
    parser.add_argument("--target_bundle_emphasis", type=str, required=True,
                        help="Emphasis setting for TARGET_BUNDLE in the proxy.")
    parser.add_argument("--anchor_num_target_bundles", type=str, required=True,
                        help="Number of target bundles to anchor in the proxy.")

    args = parser.parse_args()

    # Load environment variables
    load_dotenv(dotenv_path=args.env_path)
    print(f"[INFO] Loaded environment variables from {args.env_path}")

    # Prepare a timestamp
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    overall_log_df = pd.DataFrame()
    rows = []

    # Prepare the PureLLM-G proxy factory with arguments
    def purellm_g_proxy_factory_constructor():
        return CECA_PureLLM_G_Proxy_Factory(
            check_priority=args.check_priority,
            target_bundle_priority=args.target_bundle_priority,
            happy_priority=args.happy_priority,
            target_bundle_emphasis=args.target_bundle_emphasis,
            anchor_num_target_bundles=args.anchor_num_target_bundles,
            cap=args.cap,
            min_iterations=args.min_iterations,
        )

    # Discover scenario+setup combinations
    tasks = discover_scenarios_and_setups(args.benchmark)
    if not tasks:
        print("[WARN] No scenarios or setups discovered. Exiting.")
        return

    print(f"[INFO] Discovered {len(tasks)} scenario+setup tasks to run.")

    # Number of workers (adjust as needed)
    max_workers = min(12, len(tasks))

    # Process each scenario+setup in parallel
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for (scenario_code, setup_index) in tasks:
            # Build the factory in the main process, pass the instance to each worker
            proxy_factory = purellm_g_proxy_factory_constructor()
            futures.append(
                executor.submit(
                    process_scenario,
                    args.benchmark,
                    scenario_code,
                    setup_index,
                    proxy_factory,
                    timestamp
                )
            )

        for future in concurrent.futures.as_completed(futures):
            row, log_df = future.result()
            if row is not None and log_df is not None:
                rows.append(row)
                overall_log_df = pd.concat([overall_log_df, log_df], ignore_index=True)

    # Mark the log DataFrame with identifying info
    overall_log_df["Proxy"] = "Proxy-VD1"
    overall_log_df["Proxy-check_priority"] = args.check_priority
    overall_log_df["Proxy-target_bundle_priority"] = args.target_bundle_priority
    overall_log_df["Proxy-happy_priority"] = args.happy_priority
    overall_log_df["Proxy-target_bundle_emphasis"] = args.target_bundle_emphasis
    overall_log_df["Proxy-anchor_num_target_bundles"] = args.anchor_num_target_bundles
    overall_log_df["Timestamp"] = timestamp

    # Create the output directory if needed
    out_dir = f"data/{args.benchmark}-logs"
    os.makedirs(out_dir, exist_ok=True)

    # Save the logs to CSV
    log_filename = os.path.join(out_dir, f"log_Proxy-VD1_{timestamp}.csv")
    overall_log_df.to_csv(log_filename, index=False)

    print(f"[INFO] Processing complete. Logs saved to {log_filename}")


if __name__ == "__main__":
    main()
