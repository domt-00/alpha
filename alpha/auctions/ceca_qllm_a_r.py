"""
NVD proxy with two efficiency improvements:

1. Bundle restriction — before the first valuation refresh, one LLM call
   identifies which item types the person plausibly cares about. All future
   refreshes skip bundles containing only irrelevant item types, reducing
   wasted LLM calls on bundles the person would never bid on.

2. Trend pruning — after each refresh, bundles whose inferred value falls
   in the bottom percentile are flagged and excluded from future refreshes.
   This prevents repeatedly querying bundles that have consistently looked
   worthless across iterations.

Together these reduce the number of value_query calls per CECA iteration
while keeping the highest-value bundles accurately estimated.
"""

from typing import Literal
from pydantic import BaseModel, Field
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

from alpha.util import get_llm_client, get_llm_model, get_llm_provider, parse_structured_output, retry
from alpha.proxy import ProxyFactory
from alpha.person import Person
from alpha.scenario import scenario_all_bundles
from alpha.auctions.ceca_qllm_a import CECA_QLLM_A_Proxy


class ReasonableItems(BaseModel):
    reasoning: str = Field(
        description="Brief reasoning about which item types match this person's "
                    "preferences, budget, and described needs."
    )
    item_type_codes: list[str] = Field(
        description="Item type codes from the available list that this person would "
                    "plausibly want to bid on. Be inclusive — if uncertain, include it."
    )


class CECA_QLLM_A_R_Proxy(CECA_QLLM_A_Proxy):
    """
    NVD proxy with bundle restriction + trend pruning.

    Inherits the full NVD bidding and question logic. Only the valuation
    refresh is changed: it queries fewer bundles each iteration by (a)
    restricting to item types the person cares about and (b) skipping
    bundles that have consistently shown low value in prior refreshes.
    """

    def __init__(self,
                 person: Person,
                 check_priority,
                 target_bundle_priority,
                 happy_priority,
                 target_bundle_emphasis,
                 anchor_num_target_bundles,
                 num_questions,
                 discount: float = 0.75,
                 CAP_INTERACTIONS: int = 20,
                 MIN_ITERATIONS: int = 0,
                 MAX_TRIES: int = 3,
                 prune_percentile: float = 0.25,
                 restrict: bool = True,
                 compress_description: bool = False):
        super().__init__(
            person, check_priority, target_bundle_priority,
            happy_priority, target_bundle_emphasis, anchor_num_target_bundles,
            num_questions, discount, CAP_INTERACTIONS, MIN_ITERATIONS, MAX_TRIES,
            compress_description=compress_description,
        )
        # None = not yet fetched; set immediately to all codes if restriction disabled
        self._reasonable_codes: set[str] | None = None if restrict else set(person.scenario.codes())
        self._pruned_bundles: set[str] = set()
        self.prune_percentile = prune_percentile
        self.restrict = restrict

    # ── Bundle restriction ────────────────────────────────────────────────────

    @retry()
    def _fetch_reasonable_codes(self) -> set[str]:
        """Single LLM call to identify which item types this person cares about."""
        valid_codes = self.person.scenario.codes()
        messages = [{
            "role": "user",
            "content": (
                "You are representing a person in a combinatorial auction.\n\n"
                "Scenario:\n" + self.person.scenario.Description() + "\n\n"
                "Person's description:\n" + str(self.person.seed) + "\n\n"
                "Available item types (use these exact codes): "
                + ", ".join(valid_codes) + "\n\n"
                "Which of these item types is this person plausibly interested "
                "in bidding on? Include a type if there is any reasonable chance "
                "the person would want it. Only exclude types that clearly do not "
                "match the person's described needs or budget at all."
            )
        }]
        client = get_llm_client()
        result = parse_structured_output(client, get_llm_model(), messages, ReasonableItems)
        # Intersect with valid codes to prevent hallucinated codes
        codes = {c for c in result.item_type_codes if c in valid_codes}
        # Fallback: if LLM returns nothing valid, include all
        return codes if codes else set(valid_codes)

    def _is_reasonable_bundle(self, bundle) -> bool:
        if not self._reasonable_codes:
            return True
        return any(
            qty > 0 and item_type.code in self._reasonable_codes
            for item_type, qty in zip(bundle.scenario.item_types, bundle.quantities)
        )

    # ── Overridden refresh with restriction + pruning ─────────────────────────

    def refresh_inferred_valuations(self):
        # Lazy init: one LLM call on first refresh to identify relevant item types
        if self._reasonable_codes is None:
            try:
                self._reasonable_codes = self._fetch_reasonable_codes()
            except Exception:
                self._reasonable_codes = set(self.person.scenario.codes())

        new_inferred_valuations = {}
        all_bundles = scenario_all_bundles(self.person.scenario)

        bundles_to_query = [
            b for b in all_bundles
            if not any(b == b2 for b2, _ in self.manifest_valuation.atomic_bids)
            and self._is_reasonable_bundle(b)
            and str(b) not in self._pruned_bundles
        ]

        max_workers = 1 if get_llm_provider() == "ollama" else (min(10, len(bundles_to_query)) if bundles_to_query else 1)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_bundle = {executor.submit(self.value_query, b): b for b in bundles_to_query}
            for future in tqdm(as_completed(future_to_bundle), total=len(future_to_bundle), desc="Refreshing Valuations (R)"):
                bundle = future_to_bundle[future]
                try:
                    value = future.result()
                    new_inferred_valuations[bundle] = int(value * self.discount)
                except Exception:
                    pass

        self.inferred_valuations = new_inferred_valuations

        # Trend pruning: flag bottom-percentile bundles for exclusion in future refreshes
        if self.inferred_valuations and self.prune_percentile > 0:
            values = sorted(self.inferred_valuations.values())
            cutoff_idx = int(len(values) * self.prune_percentile)
            if cutoff_idx > 0:
                threshold = values[cutoff_idx - 1]
                for b, v in self.inferred_valuations.items():
                    if v <= threshold:
                        self._pruned_bundles.add(str(b))


class CECA_QLLM_A_R_Proxy_Factory(ProxyFactory):
    """Base factory — configure restrict and prune_percentile to select variant."""

    def __init__(self,
                 check_priority: str,
                 target_bundle_priority: str,
                 happy_priority: str,
                 target_bundle_emphasis: str,
                 anchor_num_target_bundles: str,
                 num_questions: int,
                 cap: int,
                 min_iterations: int,
                 prune_percentile: float = 0.25,
                 restrict: bool = True,
                 compress_description: bool = False):
        self.check_priority = check_priority
        self.target_bundle_priority = target_bundle_priority
        self.happy_priority = happy_priority
        self.target_bundle_emphasis = target_bundle_emphasis
        self.anchor_num_target_bundles = anchor_num_target_bundles
        self.num_questions = num_questions
        self.cap = cap
        self.min_iterations = min_iterations
        self.prune_percentile = prune_percentile
        self.restrict = restrict
        self.compress_description = compress_description

    def __call__(self, person: Person) -> CECA_QLLM_A_R_Proxy:
        return CECA_QLLM_A_R_Proxy(
            person,
            self.check_priority,
            self.target_bundle_priority,
            self.happy_priority,
            self.target_bundle_emphasis,
            self.anchor_num_target_bundles,
            self.num_questions,
            CAP_INTERACTIONS=self.cap,
            MIN_ITERATIONS=self.min_iterations,
            prune_percentile=self.prune_percentile,
            restrict=self.restrict,
            compress_description=self.compress_description,
        )


class CECA_QLLM_A_Restrict_Factory(CECA_QLLM_A_R_Proxy_Factory):
    """Bundle restriction only — no trend pruning."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("prune_percentile", 0.0)
        kwargs.setdefault("restrict", True)
        super().__init__(*args, **kwargs)


class CECA_QLLM_A_Prune_Factory(CECA_QLLM_A_R_Proxy_Factory):
    """Trend pruning only — no bundle restriction."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("prune_percentile", 0.25)
        kwargs.setdefault("restrict", False)
        super().__init__(*args, **kwargs)
