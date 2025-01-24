import os
import json
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dotenv import load_dotenv

from alpha.scenario import scenarios
from alpha.seed_generation.v5 import SeedGenerationPipeline_v5
from alpha.persons.full_person import FullPerson


def process_seed(scenario, benchmark, seed, setup_index):
    """
    Process a single seed:
    - Dump the seed to a JSON file.
    - Create a FullPerson instance and dump it to a JSON file.
    """
    print("Making seed", scenario.code, benchmark, seed, setup_index)

    scenario_code = scenario.code
    # Example directory path: data/<benchmark>/<SCENARIO>/<setup_index>/
    base_dir = f"data/{benchmark}/{scenario_code}/{setup_index}"
    os.makedirs(base_dir, exist_ok=True)

    seed_json_path = os.path.join(base_dir, f"{seed.code}.json")
    fullperson_json_path = os.path.join(base_dir, f"FullPerson-{seed.code}.json")

    # Dump seed to JSON
    with open(seed_json_path, "w") as seed_file:
        json.dump(json.loads(seed.to_json()), seed_file)

    # Create and dump FullPerson
    fp = FullPerson(scenario, seed)
    with open(fullperson_json_path, "w") as f:
        json.dump(json.loads(fp.to_json()), f)
    print("Done making seed", scenario.code, benchmark, seed, setup_index)



def get_args():
    parser = argparse.ArgumentParser(description="Script for scenario generation and processing.")
    
    # New argument to specify the .env file path
    parser.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="Path to the .env file (default: .env)"
    )
    
    parser.add_argument(
        "--scenarios",
        type=str,
        default=None,
        help="Comma-separated list of scenario codes, e.g. TRANSPORTATION,ELECTRONICS."
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        default=None,
        help="Name of the benchmark (e.g. 'round3')."
    )
    parser.add_argument(
        "--num_setups",
        type=int,
        default=None,
        help="Number of setups per scenario."
    )
    parser.add_argument(
        "--num_people",
        type=int,
        default=None,
        help="Number of people (seeds) per setup."
    )
    return parser.parse_args()


def main():
    args = get_args()
    
    # Load the environment variables from the specified .env file
    load_dotenv(args.env_file)
    
    # For each argument, use the command-line value if present.
    # Otherwise, read from environment variables.
    # If still None, fall back to a default.

    scenario_codes_str = args.scenarios or os.getenv("SCENARIOS")
    if not scenario_codes_str:
        raise ValueError("No scenarios provided via --scenarios or SCENARIOS env variable.")

    benchmark = args.benchmark or os.getenv("BENCHMARK", "round3")
    
    # Convert string env var to int, or fallback
    num_setups_str = args.num_setups or os.getenv("NUM_SETUPS")
    num_setups = int(num_setups_str) if num_setups_str else 3

    num_people_str = args.num_people or os.getenv("NUM_PEOPLE")
    num_people = int(num_people_str) if num_people_str else 3
    
    # Split scenario codes by comma
    scenario_codes = [s.strip() for s in scenario_codes_str.split(",")]

    # Filter only the scenarios whose .code is in the provided list
    filtered_scenarios = [sc for sc in scenarios if sc.code in scenario_codes]
    
    print("Making benchmarks for scenarios ", filtered_scenarios)

    # Number of worker processes; adjust based on your CPU cores
    max_workers = os.cpu_count() or 4

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # For each scenario in the filtered list
        for scenario in filtered_scenarios:
            # Number of total seeds = num_setups * num_people
            total_seeds = num_setups * num_people

            # Generate seeds
            seeds = SeedGenerationPipeline_v5().generate(scenario, total_seeds)

            # Prepare tasks for parallel execution
            futures = []
            for i, seed in enumerate(seeds):
                # Determine which setup index this seed belongs to
                setup_index = i // num_people
                futures.append(
                    executor.submit(
                        process_seed,
                        scenario,
                        benchmark,
                        seed,
                        setup_index
                    )
                )

            # Optionally, monitor the progress
            for future in as_completed(futures):
                try:
                    future.result()  # Raises exception if any occurred
                except Exception as e:
                    print(f"Error processing seed: {e}")


if __name__ == "__main__":
    main()
