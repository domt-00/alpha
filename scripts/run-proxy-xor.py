import os
import pandas as pd
from datetime import datetime
import argparse
from dotenv import load_dotenv
import concurrent.futures

from alpha.auctions.ceca import CECA_XOR, CECA_XOR_Elicitation_Proxy_Factory
from alpha.persons.full_person import FullPerson
from alpha.scenario import scenarios
from alpha.util import setup_logging, token_tracker

def get_scenario_by_code(code):
    """Return the scenario object (from alpha.scenario) matching the given code."""
    for s in scenarios:
        if s.code == code:
            return s
    return None

def process_scenario(benchmark, scenario_code, setup_index, proxy_factory, timestamp):
    """
    Worker function to process a single scenario + setup combination.

    Args:
        benchmark (str): The benchmark name (e.g. 'round3').
        scenario_code (str): The code of the scenario directory.
        setup_index (str or int): The setup folder name (e.g. '0', '1', '2', ...).
        proxy_factory: The proxy factory instance.
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

        # Read each FullPerson and the corresponding TruthFullPerson file
        for fp_file in fullperson_files:
            full_fp_path = os.path.join(directory, fp_file)

            with open(full_fp_path, "r") as f:
                p = FullPerson.from_json(f.read())
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

        # Prepare a single summary row
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

        # Convert the auction log (list of dicts) to a DataFrame
        log_df = pd.DataFrame(auction.log_rows)
        log_df["scenario"] = scenario_code
        log_df["setup_index"] = setup_index

        return row, log_df

    except Exception as e:
        print(f"Error processing scenario={scenario_code}, setup={setup_index}: {e}")
        return None, None


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
        # For each discovered setup subdirectory, add a task
        for setup_index in setup_subdirs:
            tasks.append((scenario_code, setup_index))

    return tasks


def _init_worker(env_path):
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path, override=True)


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="Process scenarios with environment variables from a .env file.")
    parser.add_argument("--env_path", type=str, default=".env", help="Path to the .env file to load environment variables from.")
    parser.add_argument("--benchmark", type=str, required=True, help="Name of the benchmark (e.g. 'round3').")
    args = parser.parse_args()
    token_tracker.set_context(benchmark=args.benchmark, stage="PROXY-XOR")

    # Load environment variables
    load_dotenv(dotenv_path=args.env_path)
    print(f"[INFO] Loaded environment variables from {args.env_path}")

    # Prepare a timestamp for log files
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    overall_log_df = pd.DataFrame()
    rows = []

    # Initialize the proxy factory
    proxy_factory = CECA_XOR_Elicitation_Proxy_Factory()

    # Discover scenario+setup combinations
    tasks = discover_scenarios_and_setups(args.benchmark)
    if not tasks:
        print("[WARN] No scenarios or setups discovered. Exiting.")
        return

    print(f"[INFO] Discovered {len(tasks)} scenario+setup tasks to run.")

    # Define the number of workers; adjust as needed
    max_workers = min(12, len(tasks))

    # Process each scenario+setup in parallel
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers, initializer=_init_worker, initargs=(args.env_path,)) as executor:
        futures = [
            executor.submit(process_scenario, args.benchmark, scenario_code, setup_index, proxy_factory, timestamp)
            for (scenario_code, setup_index) in tasks
        ]
        for future in concurrent.futures.as_completed(futures):
            row, log_df = future.result()
            if row is not None and log_df is not None:
                rows.append(row)
                overall_log_df = pd.concat([overall_log_df, log_df], ignore_index=True)

    # Add additional columns to the log DataFrame
    overall_log_df["Proxy"] = "Proxy-XOR"
    overall_log_df["Timestamp"] = timestamp
    overall_log_df["Provider"] = "deterministic"
    overall_log_df["Model"] = "xor"

    # Save the logs and results to CSV files
    log_filename = f"data/{args.benchmark}-logs/log_Proxy-XOR_{timestamp}.csv"
    os.makedirs(f"data/{args.benchmark}-logs/", exist_ok=True)
    overall_log_df.to_csv(log_filename, index=False)

    print(f"[INFO] Processing complete. Logs saved to {log_filename}")


if __name__ == "__main__":
    main()
