import itertools
import json
import random
import concurrent.futures
from typing import Optional
from functools import partial


from pydantic import BaseModel, Field

from alpha.agent import MessageDecorator
from alpha.person import Person, Seed
from alpha.persons.standard_person import (
    StandardQuestionPipeline,
    StandardValuePipeline,
)
from alpha.scenario import Bundle, Scenario, scenario_bundle_sample
from alpha.xor import XORBid

def process_bundle(scenario, seed, quantities_tuple):
    quantities = list(quantities_tuple)
    try:
        bundle = Bundle(scenario=scenario, quantities=quantities)
        value = StandardValuePipeline()(
            scenario=scenario, seed=seed, bundle=bundle
        )
        return bundle, value
    except Exception as e:
        # Log the exception and skip this bundle
        return None


class BundleModel(BaseModel):
    reasoning: str = Field(description="Reasoning for giving this bundle")
    bundle_idx: int = Field(description="Bundle index")
    item_type_codes: list[str] = Field(
        description="A list of codes identifying the item type. Only give each item type code once. For multiples of the same item, indicate it in item_quantities."
    )
    item_quantities: list[int] = Field(
        description="A list of quantities identify the amount of the corresponding item type. Ensure that the item quantity here is less than or equal to the total quantity available"
    )


class ListOfBundleModel(BaseModel):
    reasoning: str = Field(
        description="Process and criteria for choosing the list of bundles"
    )
    bundles: list[BundleModel] = Field(description="The list of bundles.")
    


class FullPerson(Person):
    """
    Person where all possible bundles are considered. Value and demand
    queries are optimized to target all possible bundles.
    """

    def __init__(
        self,
        scenario: Scenario,
        seed: Seed,
        demand_mode: str = "MAX",
        given_valuation: Optional[XORBid] = None,
        max_workers: Optional[int] = 4,  # Optional parameter to control parallelism
    ):
        self.scenario = scenario
        self.seed = seed
        self.demand_mode = demand_mode

        self.value_pipeline = StandardValuePipeline()
        self.question_pipeline = StandardQuestionPipeline()

        N = len(self.scenario)  # Number of item types in the scenario

        if given_valuation:
            self.XOR_Valuation = given_valuation
        else:
            # Generate all possible bundles (combinations of item quantities)
            sorted_product = sorted(itertools.product([0, 1], repeat=N), key=sum)

            self.XOR_Valuation = XORBid()

            # Use ProcessPoolExecutor for CPU-bound tasks
            with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                # Create a partial function with scenario and seed
                partial_process_bundle = partial(process_bundle, scenario, seed)
                
                # Map the sorted_product to the partial_process_bundle function
                results = executor.map(partial_process_bundle, sorted_product)

                # Iterate through the results and add valid bids
                for result in results:
                    if result is not None:
                        bundle, value = result
                        self.XOR_Valuation.add_atomic_bid(bundle, value)

    @MessageDecorator(cache = False)
    def Message(self, message_type: str, params: any, logger=None):
        if message_type == "question":
            return self.question_pipeline(
                scenario=self.scenario,
                seed=self.seed,
                question=params["question"],
                logger=logger,
            )
        elif message_type == "value":
            return self.XOR_Valuation.evaluate(params["bundle"])
        elif message_type == "demand":
            current_bundle_utility = self.XOR_Valuation.evaluate(
                params["bundle"]
            ) - params["prices"](params["bundle"])

            bundles = [
                bundle for bundle, _ in self.XOR_Valuation.atomic_bids
            ] + scenario_bundle_sample(
                self.scenario, 2**(len(self.scenario)) - len(self.XOR_Valuation.atomic_bids) - 1, seed=None
            )
            bundles = [bundle for bundle in bundles if bundle != params["bundle"]]

            utilities = [
                self.XOR_Valuation.evaluate(bundle) - params["prices"](bundle)
                for bundle in bundles
            ]

            if max(utilities) <= current_bundle_utility:
                return params["bundle"]
            else:
                if self.demand_mode == "RAND":
                    possible_bundles = [
                        bundle
                        for bundle, utility in zip(bundles, utilities)
                        if utility > current_bundle_utility
                    ]
                    return random.choice(possible_bundles)
                else:
                    possible_bundles = [
                        bundle
                        for bundle, utility in zip(bundles, utilities)
                        if utility == max(utilities)
                    ]
                    return random.choice(possible_bundles) 

    def to_json(self):
        return json.dumps(
            {
                "scenario": self.scenario.to_json(),
                "seed": self.seed.to_json(),
                "xor_valuation": self.XOR_Valuation.to_json(),
            }
        )

    @staticmethod
    def from_json(json_str):
        data = json.loads(json_str)
        if isinstance(data, str):
            data = json.loads(data)
        scenario = Scenario.from_json(data["scenario"])
        seed = Seed.from_json(data["seed"])
        xor_valuation = XORBid.from_json(data["xor_valuation"])
        return FullPerson(
            scenario=scenario, seed=seed, given_valuation=xor_valuation
        )