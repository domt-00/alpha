"""
make-fullpersons.py
-------------------
Loads existing seed JSON files from disk and generates FullPerson files
(64 bundle valuations each) without re-generating the seeds.

Picks up any seeds that already have a seed JSON but no FullPerson JSON.

Usage:
    cd "DT Study"
    python scripts/make-fullpersons.py --benchmark first
"""

import os
import json
import argparse
from dotenv import load_dotenv
from concurrent.futures import ProcessPoolExecutor, as_completed

from alpha.scenario import scenarios
from alpha.person import Seed
from alpha.persons.full_person import FullPerson


def get_scenario_by_code(code):
    for s in scenarios:
        if s.code == code:
            return s
    return None


def process_seed(scenario_code, benchmark, setup_index, seed_path, env_file=".env"):
    """Load one seed from disk and generate its FullPerson file."""
    load_dotenv(env_file, override=True)

    scenario = get_scenario_by_code(scenario_code)
    if not scenario:
        print(f"[ERROR] Unknown scenario: {scenario_code}")
        return

    with open(seed_path) as f:
        seed = Seed.from_json(json.dumps(json.load(f)))

    base_dir = f"data/{benchmark}/{scenario_code}/{setup_index}"
    fullperson_path = os.path.join(base_dir, f"FullPerson-{seed.code}.json")

    if os.path.exists(fullperson_path):
        print(f"[SKIP] FullPerson-{seed.code}.json already exists")
        return

    print(f"[INFO] Building FullPerson for {seed.code} ({scenario_code}/{setup_index}) — 64 bundle queries...")

    try:
        fp = FullPerson(scenario, seed)
        with open(fullperson_path, "w") as f:
            json.dump(json.loads(fp.to_json()), f, indent=2)
        print(f"[DONE] Saved FullPerson-{seed.code}.json")
    except Exception as e:
        print(f"[ERROR] Failed for {seed.code}: {e}")


def discover_seeds(benchmark):
    """Find all seed JSON files that don't yet have a FullPerson file."""
    base_dir = os.path.join("data", benchmark)
    tasks = []

    for scenario_code in os.listdir(base_dir):
        scenario_path = os.path.join(base_dir, scenario_code)
        if not os.path.isdir(scenario_path):
            continue

        for setup_index in os.listdir(scenario_path):
            setup_path = os.path.join(scenario_path, setup_index)
            if not os.path.isdir(setup_path):
                continue

            for fname in os.listdir(setup_path):
                # Seed files: e.g. dianaanderson.json (NOT starting with FullPerson)
                if fname.endswith(".json") and not fname.startswith("FullPerson") and not fname.startswith("."):
                    seed_path = os.path.join(setup_path, fname)
                    fp_path = os.path.join(setup_path, f"FullPerson-{fname}")

                    if not os.path.exists(fp_path):
                        tasks.append((scenario_code, setup_index, seed_path))

    return tasks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=str, default="first")
    parser.add_argument("--env-file", type=str, default=".env")
    args = parser.parse_args()

    load_dotenv(args.env_file)

    tasks = discover_seeds(args.benchmark)

    if not tasks:
        print("[INFO] No seeds missing FullPerson files. All done.")
        return

    print(f"[INFO] Found {len(tasks)} seeds needing FullPerson generation:")
    for scenario_code, setup_index, seed_path in tasks:
        print(f"  {scenario_code}/{setup_index}/{os.path.basename(seed_path)}")
    print()

    # Run one at a time to avoid hammering the rate limit
    # (each FullPerson = 64 LLM calls — parallel would blow through rate limits)
    for scenario_code, setup_index, seed_path in tasks:
        process_seed(scenario_code, args.benchmark, setup_index, seed_path, env_file=args.env_file)

    print("\n[INFO] All FullPerson files generated.")


if __name__ == "__main__":
    main()
