import itertools
import json

from alpha.scenario import TransportationScenario, bundleAContainsB, Bundle


class XORBid:
    def __init__(self, atomic_bids=None):
        # atomic_bids is an optional argument. If provided, initialize with it, otherwise initialize with an empty list.
        self.atomic_bids = atomic_bids if atomic_bids else []

    def add_atomic_bid(self, bundle, value):
        
        self.atomic_bids = [(bundle_, value) for bundle_, value in self.atomic_bids if bundle_ != bundle]
        self.atomic_bids.append((bundle, value))

    def evaluate(self, bundle):
        if len(self.atomic_bids) == 0:
            return 0
        realized_values = [value for a_bundle, value in self.atomic_bids if bundleAContainsB(bundle, a_bundle)]
        return max(realized_values + [0])
    
    def __str__(self):
        if len(self.atomic_bids) > 0:
            return " XOR ".join([
                f"({bundle}, {value})" for bundle, value in self.atomic_bids
            ])
        else:
            return "No atomic bids"
        
    def __gt__(self, other):
        for b_bundle, b_value in other.atomic_bids:
            corresponding_bids = [a_value for a_bundle, a_value in self.atomic_bids if a_bundle == b_bundle]
            if not corresponding_bids or max(corresponding_bids) < b_value:
                return False

        for a_bundle, a_value in self.atomic_bids:
            corresponding_bids = [b_value for b_bundle, b_value in other.atomic_bids if b_bundle == a_bundle]
            if not corresponding_bids or a_value > max(corresponding_bids):
                return True

        return False
    
    def copy(self):
        new_bid = XORBid()
        new_bid.atomic_bids = self.atomic_bids[:]
        return new_bid
    
    def xor_diff(self, other):
        differing_bids = []
        for a_bundle, a_value in self.atomic_bids:
            corresponding_bids = [b_value for b_bundle, b_value in other.atomic_bids if b_bundle == a_bundle]
            if not corresponding_bids or corresponding_bids[0] != a_value:
                differing_bids.append((a_bundle, a_value, 'A'))

        for b_bundle, b_value in other.atomic_bids:
            corresponding_bids = [a_value for a_bundle, a_value in self.atomic_bids if a_bundle == b_bundle]
            if not corresponding_bids or corresponding_bids[0] != b_value:
                differing_bids.append((b_bundle, b_value, 'B'))

        if differing_bids:
            print("Differing atomic bids:")
            for bundle, value, source in differing_bids:
                print(f"Bundle: {bundle}, Value: {value}, Source: {source}")
        else:
            print("No differences between the XOR bids.")
    
    def to_json(self):
        return json.dumps({
            "atomic_bids": [
                {"bundle": bundle.to_json(), "value": value} 
                for bundle, value in self.atomic_bids
            ]
        })

    @staticmethod
    def from_json(json_str):
        data = json.loads(json_str)
        atomic_bids = [(Bundle.from_json(bid["bundle"]), bid["value"]) for bid in data["atomic_bids"]]
        return XORBid(atomic_bids)
    
def learn_step(scenario, seed, xor_bid):
    from .person import value_query
    
    N = len(scenario)
    
    def equivalence_query(h):
        
        sorted_product = sorted(itertools.product([0, 1], repeat=N), key=sum)
        
        for x in sorted_product:
            bundle = ";".join(str(i) for i in x)
            
            xor_value = h.evaluate(bundle)
            bidder_value = value_query(scenario, seed, bundle)
            
            if abs(bidder_value-xor_value) > 1e-3:
                if xor_value > bidder_value and \
                    any([
                        bundleAContainsB(bundle, qs_)
                        for qs_, _ in h.atomic_bids
                    ]):
                    continue
                else:
                    return bundle
                
        return "equivalent"
    
    response = equivalence_query(xor_bid)

    if response == "equivalent": 
        return xor_bid, "DONE"

    original_value = value_query(scenario, seed, response)

    T = [int(x) for x in response.split(";")]
    
    for i in range(len(T)):
        if T[i] == 1:
            T_ = [T[j] if i != j else 0 for j in range(len(T))]
            qs = ";".join(str(i) for i in T_)
            new_value = value_query(scenario, seed, qs)
            
            if new_value >= original_value:
                T = T_
        
    xor_bid.add_atomic_bid(";".join([str(x) for x in T]), original_value)

    return xor_bid, "NOT DONE"

def learn_xor_bid(scenario, seed):
    
    xor_bid = XORBid()
    
    DONE = False
    
    while not DONE:
        xor_bid, status = learn_step(scenario, seed, xor_bid)

        if status == "DONE":
            DONE = True
            
    return xor_bid

"""
Value query only version
"""

def V_learn_step(scenario, value_query, xor_bid):
    
    N = len(scenario.items)
    
    def equivalence_query(h):
        
        sorted_product = sorted(itertools.product([0, 1], repeat=N), key=sum)
        
        for x in sorted_product:
            bundle = ";".join(str(i) for i in x)
            
            xor_value = h.evaluate(bundle)
            bidder_value = value_query(bundle)
            
            if abs(bidder_value-xor_value) > 1e-3:
                if xor_value > bidder_value and \
                    any([
                        bundleAContainsB(bundle, qs_)
                        for qs_, _ in h.atomic_bids
                    ]):
                    continue
                else:
                    return bundle
                
        return "equivalent"
    
    response = equivalence_query(xor_bid)

    if response == "equivalent": 
        return xor_bid, "DONE"

    original_value = value_query(response)

    T = [int(x) for x in response.split(";")]
    
    for i in range(len(T)):
        if T[i] == 1:
            T_ = [T[j] if i != j else 0 for j in range(len(T))]
            qs = ";".join(str(i) for i in T_)
            new_value = value_query(qs)
            
            if new_value >= original_value:
                T = T_
        
    xor_bid.add_atomic_bid(";".join([str(x) for x in T]), original_value)

    return xor_bid, "NOT DONE"


from tqdm import tqdm
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed

def V_learn_xor_bid(scenario, value_query):
    cached_value_query = lru_cache(maxsize=None)(value_query)
    
    bundles = sorted(itertools.product([0, 1], repeat=len(scenario.items)), key=sum)
    
    # Parallelize the cache initialization using ThreadPoolExecutor
    def initialize_bundle(bundle):
        return cached_value_query(";".join(map(str, bundle)))

    with ThreadPoolExecutor() as executor:
        # Use tqdm to show progress
        futures = {executor.submit(initialize_bundle, bundle): bundle for bundle in bundles}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Initializing cache"):
            # Retrieve result to ensure the function is executed
            future.result()

    xor_bid = XORBid()
    it = 0

    # Initialize the tqdm progress bar for the learning process
    with tqdm(desc="V-learning XOR Bid", unit="iteration") as pbar:
        while True:
            it += 1
            xor_bid, status = V_learn_step(scenario, cached_value_query, xor_bid)
            pbar.update(1)
            if status == "DONE":
                break

    return xor_bid