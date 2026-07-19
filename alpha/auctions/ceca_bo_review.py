"""
CECA-BO-Review: allocation-stability variant of the Bayesian-optimization proxy.

Standalone review artifact — not part of the dissertation's reported results.
Copied and adapted from ceca_bo.py (which is left completely unmodified) to
investigate one specific question raised during review of section 3.2.11:
on the six-item Electronics scenario, the original CECA_BO_Proxy kept
querying the simulated person for 6-7 rounds after its GP's implied best
bundle had already stopped changing, because the only stopping rule was a
confidence threshold on the single most-uncertain candidate
(confidence_stop_ratio), which was not tight enough to detect that querying
further was no longer changing anything.

This variant adds a second, independent stopping rule: track the argmax
bundle implied by the proxy's own current valuation function (get_bid())
after every round, and stop once that argmax has been unchanged for
`stability_window` consecutive rounds - i.e. stop once the proxy's own
"opinion" of what its best bundle is has settled, rather than only stopping
once its uncertainty about one single candidate is small. The two stopping
rules are combined with OR: whichever condition is met first ends querying.
"""

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, WhiteKernel

from alpha.proxy import Proxy, ProxyFactory
from alpha.xor import XORBid
from alpha.agent import MessageDecorator
from alpha.person import Person
from alpha.scenario import Bundle, scenario_all_bundles, scenario_singleton_bundles


class CECA_BO_Review_Proxy(Proxy):
    """Bayesian-optimization proxy with an added allocation-stability stopping rule."""

    def __init__(self,
                 person: Person,
                 CAP_INTERACTIONS: int = 20,
                 seed_size: int = 6,
                 kappa: float = 2.0,
                 confidence_stop_ratio: float = 0.1,
                 stability_window: int = 3,
                 random_seed: int = 0):
        self.person = person
        self.CAP_INTERACTIONS = CAP_INTERACTIONS
        self.seed_size = seed_size
        self.kappa = kappa
        self.confidence_stop_ratio = confidence_stop_ratio
        self.stability_window = stability_window
        self.rng = np.random.default_rng(random_seed)

        self.manifest_valuation = XORBid()
        self.X_train: list[list[int]] = []
        self.y_train: list[float] = []
        self.gp: GaussianProcessRegressor | None = None
        self._seeded = False
        self.IS_HAPPY = False
        self.HAPPY_BUNDLE = None

        # New state for the allocation-stability stopping rule.
        self._top_bundle_history: list = []
        self._stopped_reason: str | None = None  # "confidence" or "stability", for review logging

    def RealPerson(self) -> Person:
        return self.person

    def Support(self):
        return ["ceca_xor_step"]

    def _seed_gp(self):
        """Query the person for a handful of seed bundles to bootstrap the GP.

        Unlike ceca_bo.py, seed_size is honoured even when it is smaller than
        the number of singleton bundles: the original _seed_gp unconditionally
        queried every singleton first (extra_needed = max(0, seed_size - N)
        floors at 0), so seed_size values below the singleton count (6, for
        the six-item scenario) were all silently equivalent to seed_size=6.
        Here, if seed_size <= len(singletons), a random subset of singletons
        of that size is used instead of all of them; the seed_size > N case
        is unchanged from the original (all singletons plus random extras).
        """
        scenario = self.person.scenario
        singletons = scenario_singleton_bundles(scenario)
        all_bundles = scenario_all_bundles(scenario)

        if self.seed_size <= len(singletons):
            idx = self.rng.choice(len(singletons), size=self.seed_size, replace=False)
            seeds = [singletons[i] for i in idx]
        else:
            seeds = list(singletons)
            seed_set = set(seeds)
            remaining = [b for b in all_bundles if b not in seed_set]
            extra_needed = self.seed_size - len(seeds)
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
        self._record_top_bundle()

    def _fit_gp(self):
        kernel = Matern(nu=1.5) + WhiteKernel(noise_level=1.0)
        self.gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True, n_restarts_optimizer=2)
        self.gp.fit(np.array(self.X_train), np.array(self.y_train))

    def _acquisition_pick(self, candidates: list[Bundle]):
        X = np.array([list(b.quantities) for b in candidates])
        mean, std = self.gp.predict(X, return_std=True)
        best_idx = int(np.argmax(mean + self.kappa * std))
        return best_idx, mean, std

    def _current_top_bundle(self):
        """The single bundle this proxy currently values most highly, across
        every bundle in the scenario (confirmed value where queried, GP
        posterior mean otherwise) - the proxy's own "best guess allocation"."""
        all_bundles = scenario_all_bundles(self.person.scenario)
        queried = {b: v for b, v in self.manifest_valuation.atomic_bids}
        unqueried = [b for b in all_bundles if b not in queried]
        values = dict(queried)
        if unqueried and self.gp is not None:
            X = np.array([list(b.quantities) for b in unqueried])
            preds = self.gp.predict(X)
            for bundle, pred in zip(unqueried, preds):
                values[bundle] = max(0, pred)
        if not values:
            return None
        return max(values, key=values.get)

    def _record_top_bundle(self):
        self._top_bundle_history.append(self._current_top_bundle())

    def _allocation_has_stabilised(self) -> bool:
        if len(self._top_bundle_history) < self.stability_window:
            return False
        recent = self._top_bundle_history[-self.stability_window:]
        return all(b == recent[0] for b in recent)

    def get_bid(self) -> XORBid:
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
                self._stopped_reason = self._stopped_reason or "exhausted"
                return 1, self.get_bid()

            # Allocation-stability check, evaluated before spending another
            # real interaction: has the proxy's own top bundle already settled?
            if self._allocation_has_stabilised():
                self.IS_HAPPY = True
                self.HAPPY_BUNDLE = params["bundle"]
                self._stopped_reason = "stability"
                return 1, self.get_bid()

            best_idx, mean, std = self._acquisition_pick(candidates)

            # Original confidence-based stop, unchanged from ceca_bo.py.
            if std[best_idx] < self.confidence_stop_ratio * max(1.0, abs(mean[best_idx])):
                self.IS_HAPPY = True
                self.HAPPY_BUNDLE = params["bundle"]
                self._stopped_reason = "confidence"
                return 1, self.get_bid()

            best_bundle = candidates[best_idx]
            value = self.person.Message("value", {"bundle": best_bundle})
            self.manifest_valuation.add_atomic_bid(best_bundle, value)
            self.X_train.append(list(best_bundle.quantities))
            self.y_train.append(value)
            self._fit_gp()
            self._record_top_bundle()

            return 0, self.get_bid()


class CECA_BO_Review_Proxy_Factory(ProxyFactory):

    def __init__(self,
                 cap: int,
                 seed_size: int = 6,
                 kappa: float = 2.0,
                 confidence_stop_ratio: float = 0.1,
                 stability_window: int = 3,
                 random_seed: int = 0):
        self.cap = cap
        self.seed_size = seed_size
        self.kappa = kappa
        self.confidence_stop_ratio = confidence_stop_ratio
        self.stability_window = stability_window
        self.random_seed = random_seed

    def __call__(self, person: Person) -> Proxy:
        return CECA_BO_Review_Proxy(
            person,
            CAP_INTERACTIONS=self.cap,
            seed_size=self.seed_size,
            kappa=self.kappa,
            confidence_stop_ratio=self.confidence_stop_ratio,
            stability_window=self.stability_window,
            random_seed=self.random_seed,
        )
