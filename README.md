# ALPHA: Accelerated LLM Proxy for High-efficiency Auctions

Authors: David Huang, Francisco Marmolejo-Cossío, Edwin Lock, David Parkes

## Installation instructions

1. Clone this repository.

2. Create an OpenAI account (if you don't already have one), and generate an API key.

Then add this key to an `.env` file in the root of your `alpha` directory containing:
`OPENAI_API_KEY="your api key goes here"`

For using this package for robustness checks against other models, also provide values for keys `OPENROUTER_API_KEY`, `GCP_PROJECT_ID`, and `GCP_LOCATION`.

3. Create a virtual environment and activate it
```bash
python -m venv venv
source venv/bin/activate
```

4. Install the package
```bash
pip install -e .
```

## Running the auctions
1. Activate virtual environment
```bash
cd alpha/
source venv/bin/activate
```

1. Create small benchmark to check that package is installed correctly
```bash
python scripts/make-benchmark.py \
    --scenarios TRANSPORTATION \
    --benchmark first \
    --num_setups 1 \
    --num_people 5
```

2. Create large benchmarks corresponding to experiments in paper
```bash
python scripts/make-benchmark.py \
    --scenarios TRANSPORTATION,ELECTRONICS,PRESERVES \
    --benchmark threes \
    --num_setups 3 \
    --num_people 3
```

3. Run proxies with given benchmark, e.g. `first`

3a. XOR
```bash
python scripts/run-proxy-xor.py \
    --env_path .env \
    --benchmark first
```

3b. VD1 
```bash
python scripts/run-proxy-vd1.py \
    --env_path .env \
    --benchmark first \
    --cap 129 \
    --min_iterations 128 \
    --check_priority high \
    --target_bundle_priority highest \
    --happy_priority low \
    --anchor_num_target_bundles "20 to 30" \
    --target_bundle_emphasis "Quickly explore the person's valuation and get to the essence of things"
```

3c. VD2
```bash
python scripts/run-proxy-vd2.py \
    --env_path .env \
    --benchmark first \
    --cap 129 \
    --min_iterations 128 \
    --check_priority high \
    --target_bundle_priority highest \
    --happy_priority low \
    --anchor_num_target_bundles "20 to 30" \
    --target_bundle_emphasis "Quickly explore the person's valuation and get to the essence of things"
```

3d. NVD
```bash
python scripts/run-proxy-nvd.py \
    --env_path .env \
    --benchmark first \
    --num_questions 1 \
    --cap 129 \
    --min_iterations 128 \
    --check_priority high \
    --target_bundle_priority highest \
    --happy_priority low \
    --anchor_num_target_bundles "20 to 30" \
    --target_bundle_emphasis "Quickly explore the person's valuation and get to the essence of things"
```

3e. Hybrid
```bash
python scripts/run-proxy-h.py \
    --env_path .env \
    --benchmark first \
    --cap 129 \
    --min_iterations 128 \
    --check_priority high \
    --target_bundle_priority highest \
    --happy_priority low \
    --anchor_num_target_bundles "20 to 30" \
    --target_bundle_emphasis "Quickly explore the person's valuation and get to the essence of things"
```

4. Visualize results for given benchmark, e.g. `first`

Make sure all proxies (xor, vd1, vd2, nvd, h) are run before running this.


```bash
python scripts/vis-benchmark-fig.py first \
```

## Visualizing simulated people preferences

5. Create preference shape and variability visualization

```bash
python scripts/make-vis-preferences.py \
    --env_path .env
```

6. Create preference roboustness visualization

```bash
python scripts/make-vis-robustness.py \
    --env_path .env
```