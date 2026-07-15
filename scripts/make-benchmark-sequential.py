"""
Sequential benchmark generator — generates seeds and FullPersons one at a time.
Uses direct API calls with simple retry (5 attempts, 3s delay) rather than the
class decorator which has 20-attempt exponential backoff.
Skips seed/FullPerson files that already exist.
"""
import os, json, time, itertools, re, argparse
from dotenv import load_dotenv

from alpha.scenario import scenarios, Bundle
from alpha.seed_generation.v5 import SeedGenerationPipeline_v5, Seed
from alpha.persons.full_person import FullPerson
from alpha.util import get_llm_client, get_llm_model
from alpha.xor import XORBid

VALUE_STATEMENT = """
Please always use the following five-step process whenever estimating a person's value for a given bundle given their preferences:
    1. Check if the person has explicitly stated the value for that bundle, give this if so
    2. Find the closest bundle(s) from the given bundle that the person has explicitly valued
    3. Identify the process by which the person has specified they will calculate their value
    4. Identify any other relevant criteria
    5. Factor (2), (3), and (4) in to estimate the person's value
"""

PATTERNS = [
    r"Bundle value:\s*[$£€]([0-9,]+(?:\.[0-9]+)?)`",
    r"Bundle value:\s*[$£€]([0-9,]+(?:\.[0-9]+)?)\*",
    r"Bundle value:\s*[$£€]([0-9,]+(?:\.[0-9]+)?)",
    r"[$£€]([0-9,]+(?:\.[0-9]+)?)",
]


def evaluate_bundle(scenario, seed, bundle, max_retries=5, retry_delay=3):
    """Direct API call with simple retry. Max wait: 5 * 3s = 15s per bundle."""
    if bundle.total_quantity() == 0:
        return 0

    client = get_llm_client()
    model = get_llm_model()
    messages = [{
        "role": "user",
        "content": (
            "Here is the scenario description: "
            + str(scenario)
            + ".\n\nHere is the description of a person's preferences who is interested in making a bid in this auction: "
            + str(seed)
            + ".\n\n*****\n They have the option to receive the following PROPOSED_BUNDLE of items: \n"
            + bundle.to_code_description()
            + ". *****\\ \n\nPlease give what you think the person would value this PROPOSED_BUNDLE of items at. "
            + VALUE_STATEMENT
            + "Give the final value of the bundle of the "
            + str(bundle.total_quantity())
            + " items in the following format: ```Bundle value: $[value]``` (express the value as a plain number in dollars)."
        ),
    }]

    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(
                model=model, messages=messages, max_tokens=800
            )
            content = completion.choices[0].message.content or ""
            for pat in PATTERNS:
                m = re.search(pat, content)
                if m:
                    return float(m.group(1).replace(",", ""))
            print(f"        no value in response (attempt {attempt+1}/{max_retries}), tail: {repr(content[-80:])}", flush=True)
        except Exception as e:
            print(f"        API error (attempt {attempt+1}/{max_retries}): {e}", flush=True)
        if attempt < max_retries - 1:
            time.sleep(retry_delay)

    print(f"        all {max_retries} attempts failed, skipping bundle", flush=True)
    return None


def build_valuation_in_process(scenario, seed, label=""):
    N = len(scenario)
    sorted_product = sorted(itertools.product([0, 1], repeat=N), key=sum)
    xor_bid = XORBid()
    total = len(sorted_product)

    for idx, quantities_tuple in enumerate(sorted_product):
        quantities = list(quantities_tuple)
        bundle = Bundle(scenario=scenario, quantities=quantities)
        value = evaluate_bundle(scenario, seed, bundle)
        if value is not None:
            xor_bid.add_atomic_bid(bundle, value)
        if (idx + 1) % 8 == 0 or idx == total - 1:
            print(f"      {label}bundle {idx+1}/{total} done", flush=True)

    return xor_bid


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=str, default=".env")
    parser.add_argument("--scenarios", type=str, required=True)
    parser.add_argument("--benchmark", type=str, required=True)
    parser.add_argument("--num_setups", type=int, default=3)
    parser.add_argument("--num_people", type=int, default=3)
    parser.add_argument("--sleep_between", type=float, default=5.0)
    return parser.parse_args()


def main():
    args = get_args()
    load_dotenv(args.env_file)

    scenario_codes = [s.strip() for s in args.scenarios.split(",")]
    filtered = [sc for sc in scenarios if sc.code in scenario_codes]
    if not filtered:
        raise ValueError(f"No scenarios found for codes: {scenario_codes}")

    for scenario in filtered:
        print(f"\n=== Scenario: {scenario.code} ===", flush=True)
        total_seeds = args.num_setups * args.num_people

        print(f"Generating {total_seeds} seeds...", flush=True)
        seeds = SeedGenerationPipeline_v5().generate(scenario, total_seeds)

        for i, seed in enumerate(seeds):
            setup_index = i // args.num_people
            base_dir = f"data/{args.benchmark}/{scenario.code}/{setup_index}"
            os.makedirs(base_dir, exist_ok=True)

            seed_path = os.path.join(base_dir, f"{seed.code}.json")
            fp_path = os.path.join(base_dir, f"FullPerson-{seed.code}.json")

            if not os.path.exists(seed_path):
                with open(seed_path, "w") as f:
                    json.dump(json.loads(seed.to_json()), f)

            if os.path.exists(fp_path):
                print(f"  [{i+1}/{total_seeds}] FullPerson exists, skipping: {seed.code}", flush=True)
                continue

            print(f"  [{i+1}/{total_seeds}] Generating FullPerson for {seed.code} (setup {setup_index})...", flush=True)
            try:
                xor_bid = build_valuation_in_process(scenario, seed, label=f"{seed.code} ")
                fp = FullPerson(scenario, seed, given_valuation=xor_bid)
                with open(fp_path, "w") as f:
                    json.dump(json.loads(fp.to_json()), f)
                print(f"  [{i+1}/{total_seeds}] Done: {fp_path}", flush=True)
            except Exception as e:
                print(f"  [{i+1}/{total_seeds}] ERROR for {seed.code}: {e}", flush=True)

            if i < total_seeds - 1:
                print(f"  Sleeping {args.sleep_between}s...", flush=True)
                time.sleep(args.sleep_between)

    print("\nAll done.", flush=True)


if __name__ == "__main__":
    main()
