"""
Generate FullPersons one at a time, sequentially, to avoid rate limits.
Uses a direct API call with simple retry (5 attempts, 3s delay) rather than
the class decorator which has 20-attempt exponential backoff (can wait hours).
Computes all 64 bundle valuations in the main process — no subprocess.
Only processes seeds that are missing a FullPerson file.
"""
import os, json, time, itertools, re
from dotenv import load_dotenv
load_dotenv(".env")

from alpha.scenario import scenarios, Bundle
from alpha.seed_generation.v5 import Seed
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
    r"Bundle value:\s*\$([0-9,]+(?:\.[0-9]+)?)`",
    r"Bundle value:\s*\$([0-9,]+(?:\.[0-9]+)?)\*",
    r"Bundle value:\s*\$([0-9,]+(?:\.[0-9]+)?)",
    r"\$([0-9,]+(?:\.[0-9]+)?)",
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
            + " items in the following format: ```Bundle value: $[value]```."
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
            print(f"      no value in response (attempt {attempt+1}/{max_retries}), last 80: {repr(content[-80:])}", flush=True)
        except Exception as e:
            print(f"      API error (attempt {attempt+1}/{max_retries}): {e}", flush=True)

        if attempt < max_retries - 1:
            time.sleep(retry_delay)

    print(f"      all {max_retries} attempts failed, skipping bundle", flush=True)
    return None


def build_valuation_in_process(scenario, seed):
    """Evaluate all 2^N bundles sequentially with fast retry."""
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
            print(f"      [{idx+1}/{total}] {quantities} -> {value}", flush=True)
        else:
            print(f"      [{idx+1}/{total}] {quantities} -> SKIPPED", flush=True)

    return xor_bid


def get_scenario_by_code(code):
    for s in scenarios:
        if s.code == code:
            return s
    return None


def find_missing(benchmark):
    missing = []
    base = f"data/{benchmark}"
    for scenario_code in os.listdir(base):
        scenario_path = os.path.join(base, scenario_code)
        if not os.path.isdir(scenario_path):
            continue
        scenario_obj = get_scenario_by_code(scenario_code)
        if not scenario_obj:
            print(f"[WARN] No scenario found for {scenario_code}", flush=True)
            continue
        for setup in os.listdir(scenario_path):
            setup_path = os.path.join(scenario_path, setup)
            if not os.path.isdir(setup_path):
                continue
            for f in os.listdir(setup_path):
                if f.startswith("FullPerson") or not f.endswith(".json"):
                    continue
                person_code = f[:-5]
                fp_path = os.path.join(setup_path, f"FullPerson-{person_code}.json")
                if not os.path.exists(fp_path):
                    seed_path = os.path.join(setup_path, f)
                    missing.append((scenario_obj, seed_path, fp_path, person_code, setup))
    return missing


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", required=True)
    args = parser.parse_args()

    missing = find_missing(args.benchmark)
    print(f"Found {len(missing)} missing FullPersons", flush=True)

    for i, (scenario_obj, seed_path, fp_path, person_code, setup) in enumerate(missing):
        print(f"\n[{i+1}/{len(missing)}] Generating FullPerson for {person_code} (setup {setup})", flush=True)
        try:
            with open(seed_path) as f:
                seed_data = json.load(f)
            seed = Seed.from_json(json.dumps(seed_data))

            xor_bid = build_valuation_in_process(scenario_obj, seed)
            fp = FullPerson(scenario_obj, seed, given_valuation=xor_bid)

            with open(fp_path, "w") as fh:
                json.dump(json.loads(fp.to_json()), fh)
            print(f"    Done: {fp_path}", flush=True)

            if i < len(missing) - 1:
                print("    Pausing 5s before next person...", flush=True)
                time.sleep(5)
        except Exception as e:
            print(f"    ERROR: {e}", flush=True)

    print("\nAll done.", flush=True)


if __name__ == "__main__":
    main()
