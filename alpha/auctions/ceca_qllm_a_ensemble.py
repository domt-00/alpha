"""
NVD proxy with ensemble valuation: each bundle is valued by calling the LLM
`ensemble_size` times independently (same prompt, fresh sample each time) and
taking the median. This targets valuation noise directly — the same bundle
has been observed to receive wildly different LLM valuations across repeated
calls (e.g. $1,045 vs $2,800 for the same bundle/person/context). The median
is robust to a single outlier sample without needing an explicit filtering
step.

Cost trade-off: `ensemble_size`x the value_query calls for every bundle
queried. No bundle selection/filtering is changed — this is orthogonal to
Restrict/Prune and could be combined with them.
"""

import statistics

from alpha.proxy import ProxyFactory
from alpha.person import Person
from alpha.scenario import Bundle
from alpha.auctions.ceca_qllm_a import CECA_QLLM_A_Proxy


class CECA_QLLM_A_Ensemble_Proxy(CECA_QLLM_A_Proxy):
    """
    NVD proxy where each bundle valuation is the median of `ensemble_size`
    independent LLM calls, instead of a single call.
    """

    def __init__(self, *args, ensemble_size: int = 3, **kwargs):
        super().__init__(*args, **kwargs)
        self.ensemble_size = ensemble_size

    def value_query(self, bundle: Bundle):
        values = []
        for _ in range(self.ensemble_size):
            try:
                values.append(super().value_query(bundle))
            except Exception:
                continue
        if not values:
            raise ValueError("All ensemble value_query samples failed for this bundle.")
        return statistics.median(values)


class CECA_QLLM_A_Ensemble_Proxy_Factory(ProxyFactory):
    """Base factory — configure ensemble_size to control cost/noise trade-off."""

    def __init__(self,
                 check_priority: str,
                 target_bundle_priority: str,
                 happy_priority: str,
                 target_bundle_emphasis: str,
                 anchor_num_target_bundles: str,
                 num_questions: int,
                 cap: int,
                 min_iterations: int,
                 ensemble_size: int = 3,
                 compress_description: bool = False):
        self.check_priority = check_priority
        self.target_bundle_priority = target_bundle_priority
        self.happy_priority = happy_priority
        self.target_bundle_emphasis = target_bundle_emphasis
        self.anchor_num_target_bundles = anchor_num_target_bundles
        self.num_questions = num_questions
        self.cap = cap
        self.min_iterations = min_iterations
        self.ensemble_size = ensemble_size
        self.compress_description = compress_description

    def __call__(self, person: Person):
        return CECA_QLLM_A_Ensemble_Proxy(
            person,
            self.check_priority,
            self.target_bundle_priority,
            self.happy_priority,
            self.target_bundle_emphasis,
            self.anchor_num_target_bundles,
            self.num_questions,
            CAP_INTERACTIONS=self.cap,
            MIN_ITERATIONS=self.min_iterations,
            ensemble_size=self.ensemble_size,
            compress_description=self.compress_description,
        )
