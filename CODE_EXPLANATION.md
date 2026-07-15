# Code Explanation — LLM-Powered Combinatorial Auction Simulation

## What is this research about?

The code simulates a **combinatorial auction** — an auction where multiple different items are sold
at the same time, and bidders can bid on *combinations* (bundles) of items, not just individual ones.

**Example**: Imagine selling a scooter, two bikes, and three other scooters at once.
A delivery company might want *two scooters*, a family might want *one bike*, and a student might want
*one scooter or one bike but not both*. Their values for bundles interact in complex ways.

The research question is: **can an LLM act as a stand-in for a human bidder?** Instead of running
real experiments with real people (slow, expensive), the system generates fictional bidder personas,
uses an LLM to simulate how they would value bundles, runs an auction mechanism against them,
and records the results.

The two scripts you run correspond to two phases:

1. **`make-benchmark.py`** — *Build* the simulated bidders and pre-compute their valuations
2. **`run-proxy-xor.py`** — *Run* the auction mechanism against those bidders and record outcomes

---

## The full picture in one diagram

```
make-benchmark.py
│
├─ For each person (3 people, run in parallel)
│   │
│   ├─ PHASE 1: Seed Generation (v5.py) — 4 LLM calls
│   │   ├─ Step 1: get_bids()      → Invent a persona
│   │   ├─ Step 2: revise_pref()   → Sharpen the persona
│   │   ├─ Step 3: elaborate_bid() → Add exact $ values per bundle
│   │   └─ Step 4: refine_bid()    → Add rules for complex bundles
│   │           ↓
│   │      Seed saved to: data/first/TRANSPORTATION/0/dianaanderson.json
│   │
│   └─ PHASE 2: FullPerson construction — 64 LLM calls per person
│       ├─ For every possible bundle combination (2^6 = 64):
│       │   └─ Ask LLM: "What would Diana pay for {SCHWIN + TROIK}?" → $1,200
│       └─ XOR Bid table saved to: data/first/TRANSPORTATION/0/FullPerson-dianaanderson.json
│
run-proxy-xor.py
│
└─ Load FullPerson files from disk (no LLM calls for valuation — already computed)
    ├─ Create a Proxy for each person (the auction mechanism talks to Proxies, not Persons)
    ├─ Run CECA_XOR auction mechanism
    │   ├─ Ask each Proxy questions to learn their preferences
    │   └─ Compute allocations and payments
    └─ Save results to CSV
```

---

## Part 1 — The Scenario

**File**: `alpha/scenario.py`

A `Scenario` is the definition of what is being auctioned. It holds a list of `ItemType` objects
and how many of each are available.

```python
@dataclass
class ItemType:
    code: str          # short identifier, e.g. "SCHWIN"
    description: str   # long product description

@dataclass
class Scenario:
    code: str                      # e.g. "TRANSPORTATION"
    description: str               # human-readable summary
    item_types: list[ItemType]     # the 6 items
    available_quantities: list[int] # [1, 1, 1, 1, 1, 1] — one of each
```

The TRANSPORTATION scenario has 6 items: ESCOOT1, ESCOOT2, VOLTRON (scooters) + TROIK, TITAN, SCHWIN (bikes).

A **Bundle** is a specific combination of quantities of those items:

```python
@dataclass
class Bundle:
    scenario: Scenario
    quantities: list[int]   # e.g. [0, 0, 0, 1, 0, 1] = one TROIK + one SCHWIN
```

So `[0, 0, 0, 1, 0, 1]` means: 0 ESCOOT1, 0 ESCOOT2, 0 VOLTRON, 1 TROIK, 0 TITAN, 1 SCHWIN.

With 6 items each at quantity 0 or 1, there are **2^6 = 64 possible bundles** (including the empty bundle).

---

## Part 2 — The Seed (Bidder Persona)

**File**: `alpha/person.py`

A `Seed` is a text description of a fictional person — their background, taste, budget, and how
they would evaluate items. Think of it as the character sheet for a simulated bidder.

```python
@dataclass
class Seed:
    code: str         # e.g. "dianaanderson"
    scenario: str     # e.g. "TRANSPORTATION"
    description: str  # the long markdown text you see in the terminal
```

The `description` is what you saw printed in the terminal — the paragraphs about Diana being a
budget-conscious parent who wants a SCHWIN for $700, doesn't care about scooters, etc.
This text is the entire "brain" of the simulated bidder. Every time the system needs to know
what Diana thinks about a bundle, it feeds this text to the LLM and asks.

---

## Part 3 — Seed Generation Pipeline

**File**: `alpha/seed_generation/v5.py`

This is how the Seed (persona) is created. It runs **4 LLM calls in sequence**, each building
on the previous output.

### Step 1: `get_bids(scenario)` — Invent a persona

```python
# Sends to LLM:
"There is an auction with these items: [scenario description]
Please give me three different people named Alice Smith, Bob Jones, Carol Williams."

# LLM returns JSON:
{
  "bidders": [
    {"name": "Alice Smith", "description_of_preferences": "Alice is a..."},
    {"name": "Bob Jones",   "description_of_preferences": "Bob wants..."},
    {"name": "Carol Williams", "description_of_preferences": "Carol needs..."}
  ]
}

# Code picks ONE at random → e.g. picks Diana Anderson
```

**Why generate 3 and pick 1?** More diversity — you're less likely to get the same
persona every time if the LLM has to think about multiple people simultaneously.

### Step 2: `revise_pref(pref, scenario)` — Sharpen it

```python
# Sends to LLM:
"Here is Diana's description: [step 1 output]
Identify gaps, ambiguities, and unclear willingness-to-pay.
Revise it to be more precise."

# LLM returns:
{"wtp": "...", "full_revised_preferences": "Diana is a budget-conscious parent..."}
```

This step catches things like "she wants a bike" (which bike? at what price?) and forces specificity.

### Step 3: `elaborate_bid(bid, scenario)` — Add exact dollar values

```python
# Sends to LLM:
"Here is Diana's revised description: [step 2 output]
Now enumerate specific bundles with EXACT dollar values.
Format: ``` [DESCRIPTION] ```"

# LLM returns a markdown block with things like:
# - {SCHWIN}: $700 (her top choice)
# - {TITAN}:  $550 (secondary)
# - {SCHWIN, ESCOOT1}: $0 (rejects scooter bundles)
```

This is the most important step — the persona now has concrete numbers attached to concrete bundles.
The LLM is forced to think like an economist: "what is Diana's true willingness to pay?"

### Step 4: `refine_bid(elaborated_bid, scenario)` — Add evaluation rules

```python
# Sends to LLM:
"Given Diana's description with values: [step 3 output]
How does she evaluate COMPLEX bundles?
- Are her values additive? (2 bikes = 2× one bike value?)
- Does she apply discounts for multiples?
- What discount/premium %? Quantify everything."

# LLM appends a section like:
# "Diana evaluates bundles by taking only her top-choice item.
#  A second bike has 0% additional value. Scooters are always $0..."
```

This matters for the auction because the mechanism will eventually ask about bundle combinations
Diana was never explicitly asked about. These rules allow consistent extrapolation.

### The result is saved:

```
data/first/TRANSPORTATION/0/dianaanderson.json
{
  "code": "dianaanderson",
  "scenario": "TRANSPORTATION",
  "description": "Diana is a budget-conscious parent... [1500 words]"
}
```

---

## Part 4 — FullPerson: Pre-computing All Bundle Values

**File**: `alpha/persons/full_person/core.py`

After the Seed is created, the code builds a `FullPerson`. This is where most of the LLM calls happen.

The problem: during the auction, the mechanism needs to ask "what does Diana value bundle X at?"
many times, very quickly. Calling the LLM each time mid-auction would be too slow and unreliable.

**Solution**: pre-compute Diana's value for *every single possible bundle* before the auction starts,
and store it in a lookup table called an **XOR Bid**.

```python
class FullPerson(Person):
    def __init__(self, scenario, seed, ...):
        # Generate ALL possible bundles: 2^6 = 64 for TRANSPORTATION
        sorted_product = sorted(itertools.product([0, 1], repeat=6), key=sum)
        # → [(0,0,0,0,0,0), (1,0,0,0,0,0), (0,1,0,0,0,0), ..., (1,1,1,1,1,1)]

        self.XOR_Valuation = XORBid()

        # For each bundle, ask the LLM what Diana would pay
        # This runs in parallel using ProcessPoolExecutor
        with ProcessPoolExecutor() as executor:
            results = executor.map(process_bundle, all_bundles)

        # Store all 64 (bundle, value) pairs
        for bundle, value in results:
            self.XOR_Valuation.add_atomic_bid(bundle, value)
```

Each of those 64 LLM calls looks like this:

```
"Here is Diana's full description: [~1500 words]

She has the option to receive: Items in bundle (2 total) - SCHWINx1, TROIKx1

Please use this 5-step process:
  1. Check if Diana explicitly stated a value for this bundle
  2. Find the closest bundle she has valued
  3. Identify her calculation process
  4. Identify other criteria
  5. Estimate her value

Give the final value as: ```Bundle value: $[value]```"
```

The LLM responds with something like:
```
Diana has not explicitly valued SCHWIN + TROIK together. Her closest
stated values are SCHWIN at $700 and TROIK at $0 (she finds it unnecessary).
Following her rule of only wanting one bike...

```Bundle value: $700```
```

The regex then extracts `700` from that response.

### Why XOR Bid?

An **XOR Bid** is a standard format in combinatorial auction theory. It means:
*"I bid on multiple bundles, but only ONE of them can win."*

For example, Diana's XOR bid might be:
```
({SCHWIN}, $700)  XOR  ({TITAN}, $550)  XOR  ({}, $0)  XOR ...
```

This means Diana is willing to pay $700 for SCHWIN alone, or $550 for TITAN alone,
but the auction can only give her one bundle — she can't win both.

The `evaluate(bundle)` function on the XOR bid returns the value of the best
sub-bundle that fits within the given bundle:

```python
def evaluate(self, bundle):
    # Find all atomic bids where the bid bundle is contained within the given bundle
    realized_values = [value for a_bundle, value in self.atomic_bids
                       if a_bundle is contained in bundle]
    return max(realized_values)  # return the best one
```

So if you ask "what does Diana value {SCHWIN + ESCOOT1} at?", it finds that
{SCHWIN} ⊂ {SCHWIN + ESCOOT1} → returns $700 (she just ignores the scooter).

### The result is saved:

```
data/first/TRANSPORTATION/0/FullPerson-dianaanderson.json
{
  "scenario": {...},
  "seed": {"code": "dianaanderson", "description": "..."},
  "xor_valuation": {
    "atomic_bids": [
      {"bundle": {"quantities": [0,0,0,0,0,0]}, "value": 0},
      {"bundle": {"quantities": [1,0,0,0,0,0]}, "value": 0},   ← ESCOOT1 alone = $0
      {"bundle": {"quantities": [0,0,0,0,0,1]}, "value": 700}, ← SCHWIN alone = $700
      ...all 64 bundles
    ]
  }
}
```

---

## Part 5 — The Auction Mechanism (run-proxy-xor.py)

**File**: `scripts/run-proxy-xor.py`

This script loads the pre-computed FullPerson files and runs the actual auction.

```python
# Load Diana, Quinn, Tara from disk (no new LLM calls for valuation)
persons = [FullPerson.from_json(file) for file in fullperson_files]

# Create a Proxy for each person
proxies = [proxy_factory(person) for person in persons]

# Run the auction
auction = CECA_XOR()
allocation = auction(scenario=scenario_obj, agents=proxies, persons=persons)
```

### What is a Proxy?

A `Proxy` sits between the auction mechanism and the `FullPerson`. The auction doesn't talk
to the FullPerson directly — it talks to the Proxy, which may ask the FullPerson questions
(potentially via LLM) before responding.

The point of a Proxy in this research is to simulate **information elicitation**: in a real auction,
the auctioneer doesn't know your full valuation — they ask you questions to learn it. The Proxy
mimics this by revealing Diana's preferences bit by bit, rather than all at once.

### What is CECA_XOR?

CECA stands for **Combinatorial Exchange with Communication and Allocation**. It is the auction
mechanism being tested. It:

1. Starts with no knowledge of what anyone values
2. Asks each Proxy questions ("would you pay $500 for this scooter?")
3. Uses the answers to iteratively compute who should get what
4. Eventually produces a final **allocation** (who gets which bundle) and **payments** (how much each person pays)

The output is:
```python
allocation = [
    (Bundle([0,0,0,0,0,1]), 650.0),  # Diana gets SCHWIN, pays $650
    (Bundle([1,0,0,0,0,0]), 800.0),  # Quinn gets ESCOOT1, pays $800
    (Bundle([0,0,0,1,0,0]), 1500.0), # Tara gets TROIK, pays $1,500
]
```

### Results saved to CSV

```
data/first-logs/log_Proxy-XOR_20240531120000.csv
│
├─ Each row = one round of the auction
├─ Columns: scenario, setup_index, round, prices, allocation, ...
└─ Summary: total auction value, number of human interactions per person
```

---

## Part 6 — Token Flow Summary

Every LLM call sends Diana's full description as context (~1,500 tokens). Here is the full count
for your run of `--num_people 3`:

| Phase | Who | Calls | Tokens per call | Total tokens |
|---|---|---|---|---|
| Seed generation | 3 people × 4 steps | 12 | ~2,000 | ~24,000 |
| XOR valuation | 3 people × 64 bundles | 192 | ~2,000 | ~384,000 |
| **Total** | | **204** | | **~408,000** |

This is why the free tier rate limits get hit — the valuation phase alone requires 192 calls.

---

## Part 7 — File Structure After Running

```
DT Study/
├─ data/
│   └─ first/
│       └─ TRANSPORTATION/
│           └─ 0/                          ← setup index 0
│               ├─ dianaanderson.json      ← Seed (just the text persona)
│               ├─ FullPerson-dianaanderson.json  ← all 64 bundle values
│               ├─ quinndavis.json
│               ├─ FullPerson-quinndavis.json
│               ├─ tarajones.json
│               └─ FullPerson-tarajones.json
│
└─ data/
    └─ first-logs/
        └─ log_Proxy-XOR_20240531120000.csv  ← auction results
```

---

## Part 8 — Ways to Make It More Efficient

### Problem 1: Too many LLM calls (192 for valuation)

The root cause is querying every one of 2^6 = 64 bundles per person.

**Option A — Skip obviously-zero bundles first**
Before querying all 64 bundles, ask the LLM once: "which item codes is Diana
interested in at all?" If she only cares about SCHWIN and TITAN, skip all bundles
that contain only scooters. Reduces 64 → ~10 calls for a picky bidder.

**Option B — Use the caching system that's already built in**
The `value_decorator` has a CSV cache at `~/.cache/SANDBOX_PERSON_QUERY.csv`.
If you pass `use_cache=True` when calling the value pipeline, it won't re-query
bundles it's already computed. Useful when re-running experiments.

### Problem 2: Too many tokens per call (seed description is 1,500 words)

Every valuation call sends Diana's entire persona as context. A structured 100-word
summary would work just as well for most queries and use ~15× fewer tokens.

### Problem 3: Retry delays are short

When Mistral rate-limits, the retry decorator waits 1.5s → 3s → 6s → 12s (doubling).
This eventually works but is slow. You can increase the starting delay in `util.py`:

```python
# Current:
@retry(max_attempts=20, delay=1, expansion=2)

# More patient for free-tier APIs:
@retry(max_attempts=10, delay=5, expansion=2)
# → waits 5s, 10s, 20s, 40s... much less hammering
```

### Problem 4: Parallel processes share the same API key rate limit

Both `make-benchmark.py` and `FullPerson.__init__` use `ProcessPoolExecutor` which
fires many requests simultaneously. Since they all share one API key, they all hit the
rate limit together. Running sequentially (removing the executor, just using a for loop)
would be slower but would pace the requests naturally.

---

## Quick Reference: Which file does what

| File | Purpose |
|---|---|
| `alpha/scenario.py` | Defines `Scenario`, `Bundle`, `ItemType` — the auction setup |
| `alpha/person.py` | Defines `Seed`, `FullPerson`, `XORBid` — the bidder data structures |
| `alpha/seed_generation/v5.py` | Generates a bidder persona using 4 chained LLM calls |
| `alpha/persons/full_person/core.py` | Pre-computes all 64 bundle values for one person |
| `alpha/persons/standard_person/core.py` | The LLM pipelines: value queries, question answering |
| `alpha/xor.py` | The `XORBid` data structure and learning algorithms |
| `alpha/auctions/ceca_*.py` | The auction mechanism implementations |
| `alpha/util.py` | LLM client setup, `@retry` decorator, `parse_structured_output` |
| `scripts/make-benchmark.py` | Phase 1 script: generate seeds + FullPersons → save to disk |
| `scripts/run-proxy-xor.py` | Phase 2 script: load FullPersons → run auction → save CSV |
