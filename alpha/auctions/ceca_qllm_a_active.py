"""
NVD proxy with active/uncertainty-driven bundle refresh: each value_query call
also asks the LLM for a self-reported confidence (low/medium/high). Bundles
the LLM was confident about are cached and not re-queried on subsequent
refreshes; only low/medium-confidence bundles get re-queried each cycle.

This differs from Restrict (static item-type filter) and Prune (percentile
value cutoff) in that bundle selection is driven by the model's own reported
uncertainty rather than a fixed heuristic — closer to active-learning
uncertainty sampling than to either static filter.
"""

from typing import Literal
from pydantic import BaseModel, Field
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

from alpha.util import get_llm_client, get_llm_model, get_llm_provider, parse_structured_output, retry
from alpha.proxy import ProxyFactory
from alpha.person import Person
from alpha.scenario import Bundle, scenario_all_bundles
from alpha.auctions.ceca_qllm_a import CECA_QLLM_A_Proxy


class BundleValueWithConfidence(BaseModel):
    reasoning: str = Field(description="Reasoning as to what information we have that informs this bundle's value and reasoning as to what this bundle's value is")
    value: float = Field(description="The bundle's value")
    confidence: Literal["low", "medium", "high"] = Field(
        description="How confident you are in this value estimate, given the information available. "
                    "'low' if you are largely guessing or the bundle contains items you have little "
                    "signal on; 'high' if the conversation/seed gives you strong, specific evidence "
                    "for this exact bundle or very similar ones."
    )


class CECA_QLLM_A_Active_Proxy(CECA_QLLM_A_Proxy):
    """
    NVD proxy that only re-queries low/medium-confidence bundles on refresh.
    High-confidence bundles keep their cached value, reducing repeated calls
    on bundles the model already reports being sure about.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bundle_confidence: dict[Bundle, str] = {}

    @retry(max_attempts=40, max_delay=120)
    def value_query_with_confidence(self, bundle: Bundle):
        messages = [
            {
                "role": "user",
                "content": (
                    "You helping to represent a person in a scenario where we are bidding on their behalf in an auction. "
                    + "\n\n"
                    "Here is the scenario description: \n"
                    + self.person.scenario.Description()
                    + "\n\n"
                    "Here is the description of the person's preferences: \n"
                    + self._seed_text
                    + "\n\n"
                    "Here is the current conversation history with the person: \n"
                    + (
                        "\n".join(["    " + x for x in self.conversation_history])
                        if len(self.conversation_history) > 0
                        else "    No records available."
                    )
                    + (
                        "primary conversation: \n" + "\n".join(
                            ["    " + x for x in self.primary_conversation_history]
                        )
                        if len(self.primary_conversation_history) > 0
                        else "    No records available."
                    )
                    + "\n\nPlease help me infer what you think the person value the following bundle at, "
                      "and report how confident you are in that estimate:\n"
                    + bundle.Description()
                )
            }
        ]
        client = get_llm_client()
        result = parse_structured_output(client, get_llm_model(), messages, BundleValueWithConfidence)
        return result.value, result.confidence

    def refresh_inferred_valuations(self):
        """
        First refresh: query every bundle (like plain NVD) and record confidence.
        Later refreshes: only re-query bundles whose last-known confidence was
        not "high" — high-confidence bundles keep their cached value.
        """
        all_bundles = scenario_all_bundles(self.person.scenario)
        bundles_to_query = [
            bundle for bundle in all_bundles
            if not any(bundle == bundle2 for bundle2, _ in self.manifest_valuation.atomic_bids)
            and self.bundle_confidence.get(bundle) != "high"
        ]

        new_inferred_valuations = dict(self.inferred_valuations)

        max_workers = 1 if get_llm_provider() == "ollama" else (min(10, len(bundles_to_query)) if bundles_to_query else 1)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_bundle = {
                executor.submit(self.value_query_with_confidence, bundle): bundle
                for bundle in bundles_to_query
            }
            for future in tqdm(as_completed(future_to_bundle), total=len(future_to_bundle), desc="Refreshing Valuations (active)"):
                bundle = future_to_bundle[future]
                try:
                    value, confidence = future.result()
                    new_inferred_valuations[bundle] = int(value * self.discount)
                    self.bundle_confidence[bundle] = confidence
                except Exception:
                    pass

        self.inferred_valuations = new_inferred_valuations


class CECA_QLLM_A_Active_Proxy_Factory(ProxyFactory):

    def __init__(self,
                 check_priority: str,
                 target_bundle_priority: str,
                 happy_priority: str,
                 target_bundle_emphasis: str,
                 anchor_num_target_bundles: str,
                 num_questions: int,
                 cap: int,
                 min_iterations: int,
                 compress_description: bool = False):
        self.check_priority = check_priority
        self.target_bundle_priority = target_bundle_priority
        self.happy_priority = happy_priority
        self.target_bundle_emphasis = target_bundle_emphasis
        self.anchor_num_target_bundles = anchor_num_target_bundles
        self.num_questions = num_questions
        self.cap = cap
        self.min_iterations = min_iterations
        self.compress_description = compress_description

    def __call__(self, person: Person):
        return CECA_QLLM_A_Active_Proxy(
            person,
            self.check_priority,
            self.target_bundle_priority,
            self.happy_priority,
            self.target_bundle_emphasis,
            self.anchor_num_target_bundles,
            self.num_questions,
            CAP_INTERACTIONS=self.cap,
            MIN_ITERATIONS=self.min_iterations,
            compress_description=self.compress_description,
        )
