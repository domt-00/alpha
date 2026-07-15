"""
CECA-BO: Bayesian-optimization proxy.

Architecturally different from the VD1/VD2/H/NVD family (which all use an
LLM to either confirm bundles via conversation, or value every unconfirmed
bundle directly via an LLM call). Instead:

  1. Query the simulated person directly (a real interaction — same
     `person.Message("value", ...)` call the other proxies use for confirmed
     bundles) for a small seed set of bundles: every singleton bundle plus a
     few random ones.
  2. Fit a Gaussian Process regressor over bundle-quantity vectors (each
     bundle's `.quantities` is already a fixed-length numeric vector — one
     entry per item type) using these labeled points.
  3. Bid on every bundle in the scenario using the GP posterior mean — at
     zero additional interaction or LLM cost, since GP prediction is local
     computation, not an API call.
  4. Each auction round, use an upper-confidence-bound acquisition function
     (mean + kappa * std) to decide whether spending one more real
     interaction on the currently most uncertain bundle is worthwhile, and
     stop once the GP is confident enough about the best candidate.

This targets a different resource trade-off than the NVD family: cost is
dominated by a small, fixed number of real interactions rather than growing
with the number of bundles in the scenario (NVD makes one LLM call per
bundle per refresh; here, bundle count only affects the cost of local GP
prediction, which is negligible).
"""

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, WhiteKernel

from alpha.proxy import Proxy, ProxyFactory
from alpha.xor import XORBid
from alpha.agent import MessageDecorator
from alpha.person import Person
from alpha.scenario import Bundle, scenario_all_bundles, scenario_singleton_bundles


class CECA_BO_Proxy(Proxy):
    """Bayesian-optimization proxy: GP over bundle-quantity space, fit from a
    handful of real person queries, bidding via posterior mean elsewhere."""

    def __init__(self,
                 person: Person,
                 CAP_INTERACTIONS: int = 20,
                 seed_size: int = 6,
                 kappa: float = 2.0,
                 confidence_stop_ratio: float = 0.1,
                 random_seed: int = 0):
        self.person = person
        self.CAP_INTERACTIONS = CAP_INTERACTIONS
        self.seed_size = seed_size
        self.kappa = kappa
        self.confidence_stop_ratio = confidence_stop_ratio
        self.rng = np.random.default_rng(random_seed)

        self.manifest_valuation = XORBid()
        self.X_train: list[list[int]] = []
        self.y_train: list[float] = []
        self.gp: GaussianProcessRegressor | None = None
        self._seeded = False
        self.IS_HAPPY = False
        self.HAPPY_BUNDLE = None

    def RealPerson(self) -> Person:
        return self.person

    def Support(self):
        return ["ceca_xor_step"]

    def _seed_gp(self):
        """Query the person for a handful of seed bundles to bootstrap the GP."""
        scenario = self.person.scenario
        seeds = scenario_singleton_bundles(scenario)
        all_bundles = scenario_all_bundles(scenario)
        seed_set = set(seeds)
        remaining = [b for b in all_bundles if b not in seed_set]
        extra_needed = max(0, self.seed_size - len(seeds))
        if extra_needed > 0 and remaining:
            idx = self.rng.choice(len(remaining), size=min(extra_needed, len(remaining)), replace=False)
            seeds = seeds + [remaining[i] for i in idx]

        for bundle in seeds:
            value = self.person.Message("value", {"bundle": bundle})
            self.manifest_valuation.add_atomic_bid(bundle, value)
            self.X_train.append(list(bundle.quantities))
            self.y_train.append(value)

        self._fit_gp()
        self._seeded = True

    def _fit_gp(self):
        kernel = Matern(nu=1.5) + WhiteKernel(noise_level=1.0)
        self.gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True, n_restarts_optimizer=2)
        self.gp.fit(np.array(self.X_train), np.array(self.y_train))

    def _acquisition_pick(self, candidates: list[Bundle]):
        """Pick the candidate with highest upper-confidence-bound (mean + kappa*std)."""
        X = np.array([list(b.quantities) for b in candidates])
        mean, std = self.gp.predict(X, return_std=True)
        best_idx = int(np.argmax(mean + self.kappa * std))
        return best_idx, mean, std

    def get_bid(self) -> XORBid:
        """Bid using the GP posterior mean for every bundle not already queried."""
        out_bid = self.manifest_valuation.copy()
        all_bundles = scenario_all_bundles(self.person.scenario)
        queried = {b for b, _ in out_bid.atomic_bids}
        unqueried = [b for b in all_bundles if b not in queried]
        if unqueried and self.gp is not None:
            X = np.array([list(b.quantities) for b in unqueried])
            preds = self.gp.predict(X)
            for bundle, pred in zip(unqueried, preds):
                out_bid.add_atomic_bid(bundle, max(0, int(pred)))
        return out_bid

    @MessageDecorator(cache=False)
    def Message(self, message_type: str, params: any, logger=None):
        if message_type == "ceca_xor_step":
            if not self._seeded:
                self._seed_gp()

            if (self.IS_HAPPY and self.HAPPY_BUNDLE == params["bundle"]) or \
               self.NumberOfHumanInteractions() > self.CAP_INTERACTIONS:
                return 1, self.get_bid()

            all_bundles = scenario_all_bundles(self.person.scenario)
            queried = {b for b, _ in self.manifest_valuation.atomic_bids}
            candidates = [b for b in all_bundles if b not in queried]

            if not candidates:
                self.IS_HAPPY = True
                self.HAPPY_BUNDLE = params["bundle"]
                return 1, self.get_bid()

            best_idx, mean, std = self._acquisition_pick(candidates)

            # Stop querying once the GP is confident enough about the best candidate.
            if std[best_idx] < self.confidence_stop_ratio * max(1.0, abs(mean[best_idx])):
                self.IS_HAPPY = True
                self.HAPPY_BUNDLE = params["bundle"]
                return 1, self.get_bid()

            best_bundle = candidates[best_idx]
            value = self.person.Message("value", {"bundle": best_bundle})
            self.manifest_valuation.add_atomic_bid(best_bundle, value)
            self.X_train.append(list(best_bundle.quantities))
            self.y_train.append(value)
            self._fit_gp()

            return 0, self.get_bid()


class CECA_BO_Proxy_Factory(ProxyFactory):

    def __init__(self,
                 cap: int,
                 seed_size: int = 6,
                 kappa: float = 2.0,
                 confidence_stop_ratio: float = 0.1,
                 random_seed: int = 0):
        self.cap = cap
        self.seed_size = seed_size
        self.kappa = kappa
        self.confidence_stop_ratio = confidence_stop_ratio
        self.random_seed = random_seed

    def __call__(self, person: Person) -> Proxy:
        return CECA_BO_Proxy(
            person,
            CAP_INTERACTIONS=self.cap,
            seed_size=self.seed_size,
            kappa=self.kappa,
            confidence_stop_ratio=self.confidence_stop_ratio,
            random_seed=self.random_seed,
        )
