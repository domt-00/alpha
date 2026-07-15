import re

from ortools.linear_solver import pywraplp
from tqdm import tqdm
from typing import Union, Literal
from concurrent.futures import ThreadPoolExecutor, as_completed

from pydantic import BaseModel, Field

from alpha.util import get_llm_client, get_llm_model, parse_structured_output, retry
from alpha.proxy import Proxy, ProxyFactory
from alpha.xor import XORBid
from alpha.auction import Auction, Allocation
from alpha.agent import Agent, MessageDecorator
from alpha.person import Person
from alpha.scenario import Scenario, DirectPrices, Bundle, scenario_empty_bundle, scenario_singleton_bundles, scenario_all_bundles

def describe_xorbid(x: XORBid) -> str:
    """
    Generates a comprehensive description of an XORBid instance.

    Parameters:
        x (XORBid): The XORBid instance to describe.

    Returns:
        str: A formatted string describing the XOR bid, including a brief explanation
             of how XOR bids work and details of each atomic bid.
    """
    if not x.atomic_bids:
        return "No atomic bids available."

    # Short description of how XOR bids work
    short_description = (
        "An XOR bid allows the bidder to submit multiple atomic bids, "
        "of which only one can be accepted. This ensures that the bidder "
        "does not receive multiple bundles simultaneously."
    )

    descriptions = []
    for idx, (bundle, value) in enumerate(x.atomic_bids, start=1):
        bundle_desc = bundle.to_code_description()
        descriptions.append(
            f"  Atomic Bid {idx}: Bundle [{bundle_desc}] with Value = {value}"
        )

    detailed_description = (
        "XOR Bid Description:\n" + short_description + "\n\n" + "\n".join(descriptions)
    )
    return detailed_description

class TargetBundle(BaseModel):
    type: Literal["TARGET_BUNDLE"] = Field(
        description="Select an additional bundle for the bidder to target bidding on."
    )
    item_type_codes: list[str] = Field(
        description="A list of codes identifying the item types of the items in the bundle that we are targetting. Only give each item type code once. For multiples of the same item, indicate it in item_quantities."
    )
    item_quantities: list[int] = Field(
        description="A list of quantities identifying the amount of the corresponding item types of the items in the bundle that we are targetting. Ensure that the item quantity here is less than or equal to the total quantity available"
    )
    
class CheckPriceDemand(BaseModel):
    type: Literal["CHECK"] = Field(
        description="Set as `CHECK` to check with the user what they might want at the given prices that they want more than their currently allocated bundle at the current prices."
    )

class Happy(BaseModel):
    type: Literal["HAPPY"] = Field(
        description="Set as `HAPPY` to indicate that the user will be happy with the currently allocated bundle at currently allocated prices"
    )

class Action(BaseModel):
    response: Union[TargetBundle, CheckPriceDemand, Happy]

class InformationAction(BaseModel):
    response: Union[TargetBundle, CheckPriceDemand]

class BundleValue(BaseModel):
    reasoning: str = Field(description="Reasoning as to what information we have that informs this bundles value and reasoning as to what this bundle's value is")
    value: float   = Field(description="The bundle's value")

class CECA_HybridXOR_Proxy(Proxy):
    def __init__(self, 
                 person: Person, 
                 check_priority,
                 target_bundle_priority,
                 happy_priority,
                 target_bundle_emphasis,
                 anchor_num_target_bundles,
                 discount: float = 0.75,
                 decay: float = 0.95,
                 CAP_INTERACTIONS: int = 20,
                 MIN_ITERATIONS: int = 0,
                 MAX_TRIES: int = 3):
        
        self.person = person
        
        self.SWITCH = 10
        
        # __init__ for xor elicitation proxy
        # self.manifest_valuation = XORBid(), uses the same variable, will just need to trade-off
        # end __init__ for xor elicitation proxy
        
        # __init__ for ceca_purellm_f
        self.manifest_valuation = XORBid()
        self.MAX_TRIES = MAX_TRIES
        self.MIN_ITERATIONS = MIN_ITERATIONS
        self.CAP_INTERACTIONS = CAP_INTERACTIONS
        self.discount = discount
        
        self.decay = decay
        
        self.conversation_history = []
        self.primary_conversation_history = []

        
        self.HAPPY_BUNDLE = None
        self.IS_HAPPY = False
        
        self.check_priority = check_priority
        self.target_bundle_priority = target_bundle_priority
        self.happy_priority = happy_priority
        self.target_bundle_emphasis = target_bundle_emphasis
        self.anchor_num_target_bundles = anchor_num_target_bundles
        
        self.current_num_iterations = 0
        
        self.inferred_valuations: dict[Bundle, float] = {}
        # end __init__ for ceca_purellm_f

    def RealPerson(self) -> Person:
        return self.person

    def Support(self):
        return ["ceca_xor_step"]
    
    @retry()
    def value_query(self, bundle: Bundle):
        messages = [
            {
                "role": "user",
                "content": (
                    "You helping to represent a person in a scenario where we are bidding on their behalf in an auction. "
                    + "\n\n"
                    "Here is the scenario description: \n"
                    + self.person.scenario.Description()
                    + "\n\n"
                    "Here is the current conversation history with the person: \n"
                    + (
                        "\n".join(
                            ["    " + x for x in self.conversation_history]
                        )
                        if len(self.conversation_history) > 0
                        else "    No records available."
                    )
                    + (
                                "primary conversation: \n"+ "\n".join(
                                    ["    " + x for x in self.primary_conversation_history]
                                )
                                if len(self.primary_conversation_history) > 0
                                else "    No records available."
                            )
                    + "\n\nPlease help me infer what you think the person value the following bundle at:\n"
                    + bundle.Description()
                )
            }
        ]

        client = get_llm_client()
        bundle_value = parse_structured_output(client, get_llm_model(), messages, BundleValue)

        return bundle_value.value
    
    def refresh_inferred_valuations(self):
        """
        Refreshes the inferred valuations by querying the value of each bundle in parallel.
        """
        new_inferred_valuations = {}
        all_bundles = scenario_all_bundles(self.person.scenario)
        # Filter bundles that are not already in the manifest valuation
        bundles_to_query = [
            bundle for bundle in all_bundles
            if not any(bundle == bundle2 for bundle2, _ in self.manifest_valuation.atomic_bids)
        ]
        
        # Define the number of worker threads; adjust as needed
        max_workers = min(3, len(bundles_to_query)) if bundles_to_query else 1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all value_query tasks to the executor
            future_to_bundle = {executor.submit(self.value_query, bundle): bundle for bundle in bundles_to_query}
            
            # Use tqdm to display a progress bar
            for future in tqdm(as_completed(future_to_bundle), total=len(future_to_bundle), desc="Refreshing Valuations"):
                bundle = future_to_bundle[future]
                try:
                    value = future.result()
                    new_inferred_valuations[bundle] = int(value*self.discount)
                except Exception as exc:
                    # Handle exceptions (e.g., log them)
                    pass
                    # print(f"Error querying value for bundle {bundle}: {exc}")
        
        self.inferred_valuations = new_inferred_valuations
               
    def get_bid(self):

        if not hasattr(self, "inferred_valuations"):
            self.refresh_inferred_valuations()
        elif self.current_num_iterations < self.SWITCH:
            if (self.current_num_iterations < 4) or (self.current_num_iterations % 3 == 0):
                self.refresh_inferred_valuations()
        else:
            for k, v in self.inferred_valuations.items():
                self.inferred_valuations[k] = v * self.decay
        
        out_bid = self.manifest_valuation.copy()
        
        for bundle, value in self.inferred_valuations.items():
            if not any([bundle == bundle2 for bundle2, _ in out_bid.atomic_bids]):
                if out_bid.evaluate(bundle) < value:
                    out_bid.add_atomic_bid(bundle, value)
                
        return out_bid 

    
    @retry()
    def get_next_question(self):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user", "content": ("You helping to represent a person in a scenario where we are bidding on their behalf in an auction. "
                    + "\n\n"
                    "Here is the scenario description: \n"
                    + self.person.scenario.Description()
                    + "\n\n"
                    "Here is the current conversation history with the person: \n"
                    + (
                        "\n".join(
                            ["    " + x for x in self.conversation_history]
                        )
                        if len(self.conversation_history) > 0
                        else "    No records available."
                    )
                    + (
                                "primary conversation: \n"+ "\n".join(
                                    ["    " + x for x in self.primary_conversation_history]
                                )
                                if len(self.primary_conversation_history) > 0
                                else "    No records available."
                            )
                + "\n\n"
                + 'What should the proxy ask the person next to better understand their preferences? Please make sure to get to dollar values, be strategic about what items or groups of items you ask about to maximize information. If you have a good idea of the bidders valuation in general, you can ask about specific bundles of items to better understand their preferences. Otherwise, ask a general question. Reason step by step. Give their next question -- only one -- in the following format: Question: "[question here]"'
                )
            },
        ]
        
        client = get_llm_client()

        response = client.chat.completions.create(
            model=get_llm_model(),
            messages=messages,
        )

        result = response.choices[0].message.content

        text = re.search(r'Question: "(.*)"', result).group(1)

        return text
    
    @MessageDecorator(cache=False)
    @retry()
    def Message(self, message_type: str, params: any, logger=None):
        if message_type == "ceca_xor_step":
            
            self.current_num_iterations += 1

            if (self.IS_HAPPY and self.HAPPY_BUNDLE == params["bundle"]) or self.current_num_iterations > self.CAP_INTERACTIONS:
                return 1, self.get_bid()

            if self.current_num_iterations <= 1:
                # first iteration is just ask question
                question = self.get_next_question()
                answer = self.person.Message(
                    "question",
                    {
                        "question": question
                    }
                )
                self.conversation_history.append(
                    f"Proxy: {question}"
                )
                self.conversation_history.append(
                    f"Person: {answer}"
                )
                
                self.primary_conversation_history.append(
                    f"Proxy: {question}"
                )
                self.primary_conversation_history.append(
                    f"Person: {answer}"
                )
                return 0, self.get_bid()
            
            if self.current_num_iterations < self.SWITCH:
                # begin ceca_purellm_f core step
                prices = params["prices"]
                bundle = params["bundle"]
                allocated_bundle_value =  self.person.Message(
                    "value",
                    {
                        "bundle": bundle
                    }
                )
                allocated_bundle_utility = allocated_bundle_value - prices(bundle)
                self.manifest_valuation.add_atomic_bid(bundle, allocated_bundle_value)
            
                tries = 0
                while tries < self.MAX_TRIES:
                    tries += 1
                    messages = [
                        {
                            "role": "user",
                            "content": (
                                "You helping to represent a person in a scenario where we are bidding on their behalf in an auction. "
                                + "\n\n"
                                "Here is the scenario description: \n"
                                + self.person.scenario.Description()
                                + "\n\n"
                                + "Here are the currently tracked bundles:\n"
                                + "\n".join([x.to_code_description() for x , _ in self.manifest_valuation.atomic_bids]) +"\n\n"
                                +"Here are the current prices: \n"
                                + prices.Description()
                                + "\n\n"
                                +"Here is their currently allocated bundle: " + bundle.Description()
                                + "\n\n"
                                "Here is your current conversation history: \n"
                                + (
                                    "\n".join(
                                        ["    " + x for x in self.conversation_history]
                                    )
                                    if len(self.conversation_history) > 0
                                    else "    No records available."
                                )
                                + "\n\n"
                                "Please help me identify a single bundle that the bidder might want to target to bid on. If there is no such additional bundle, just say that the bidder is happy. If you want to double-check with the bidder to see what you want, just say that too. "
                                + f"\n\nFirst let's take stock on how the bidder feels about their currently allocated bundle at current prices. If they have no currently allocated bundle or if there is no current prices it is just the start of the auction, be AGGRESSIVE in trying out target bundles. At other times, prioritize: {self.target_bundle_emphasis}. The current target bundles will be shown in conversation history: make sure you target at least {self.anchor_num_target_bundles} bundles before saying the bidder is HAPPY. You may or may not choose to CHECK their demand at the given prices. It's a good idea to do so if you feel like you are missing something. Place a {self.check_priority} priority on giving a CHECK response, a {self.target_bundle_priority} priority on giving a TARGET_BUNDLE response, and a {self.happy_priority} priority on giving a HAPPY response. You are a helpful assistant, so without giving a final response give your thinking below. {'SYSTEM NOTE - DO NOT GIVE A HAPPY RESPONSE YET, NOT ENOUGH INFORMATION USE CHECK OR TARGET_BUNDLE' if self.current_num_iterations <= self.MIN_ITERATIONS else ''}"
                            ),
                        }
                    ]
                    
                    client = get_llm_client()

                    completion = client.chat.completions.create(
                        model=get_llm_model(), messages=messages
                    )

                    messages.append(completion.choices[0].message)
                    messages.append({"role": "user", "content": "Now format to give the appropriate action of either TARGET_BUNDLE, CHECK, or HAPPY. Do not target a bundle already targetted. Here are the items and their quantities available. Do not give a bundle exceeding the available quantities " + self.person.scenario.simple_item_overview()})

                    logger.info(messages)

                    action = parse_structured_output(
                        client,
                        get_llm_model(),
                        messages,
                        InformationAction if self.current_num_iterations <= self.MIN_ITERATIONS else Action,
                    )

                    logger.info(action)

                    if action.response.type == "CHECK":
                        demanded_bundle: Bundle = self.person.Message(
                            "demand", {"prices": prices, "bundle": bundle}
                        )
                        self.conversation_history.append(
                            f'Proxy: """CHECK: At the following prices, what would you want? \n{prices.Description()}"""'
                        )
                        self.conversation_history.append(
                            f'Person: """I want this bundle, {demanded_bundle.to_code_description()}"""'
                        )

                        query_bundle= demanded_bundle
                        query_bundle_value = self.person.Message(
                            "value", {"bundle": query_bundle}
                        )

                        self.conversation_history.append(
                            f'Person: """I value it at {query_bundle_value}"""'
                        )

                        query_bundle_utility = query_bundle_value - prices(query_bundle)

                        self.conversation_history.append(
                            f'System: Current prices mean this bundle has utility {query_bundle_utility} = {query_bundle_value} - {prices(query_bundle)}; compare this to current allocated bundle utility {allocated_bundle_utility}'
                        )
                        logger.debug(self.conversation_history[-1])

                        if query_bundle_utility > allocated_bundle_utility:
                            self.manifest_valuation.add_atomic_bid(
                                query_bundle,
                                query_bundle_value
                            )
                            return 0, self.get_bid()
                    elif action.response.type == "TARGET_BUNDLE":
                        logger.info("TARGET BUNDLE")
                        try:
                            query_bundle = Bundle.from_types_quantities(
                                self.person.scenario,
                                action.response.item_type_codes,
                                action.response.item_quantities,
                            )
                        except:
                            continue
                        
                        self.conversation_history.append(
                            f'Proxy: """TARGET BUNDLE: What do you value the following bundle at? \n{query_bundle.Description()}"""'
                        )

                        if any([query_bundle == bundle for bundle, _ in self.manifest_valuation.atomic_bids]):
                            self.conversation_history.append(
                                'Person: """I have already given you a value for this bundle, skip"""'
                            )
                        else:

                            query_bundle_value = self.person.Message(
                                "value", {"bundle": query_bundle}
                            )



                            self.conversation_history.append(
                                f'Person: """I value it at {query_bundle_value}"""'
                            )

                            query_bundle_utility = query_bundle_value - prices(query_bundle)

                            self.conversation_history.append(
                                f'System: Current prices mean this bundle has utility {query_bundle_utility} = {query_bundle_value} - {prices(query_bundle)}; compare this to current allocated bundle utility {allocated_bundle_utility}'
                            )
                            logger.debug(self.conversation_history[-1])

                            if query_bundle_utility > allocated_bundle_utility:
                                self.manifest_valuation.add_atomic_bid(
                                    query_bundle,
                                    query_bundle_value
                                )
                                return 0, self.get_bid()
                    else:
                        logger.info("HAPPY")
                        self.conversation_history.append(
                            "Proxy -> Auction: HAPPY"
                        )
                        self.IS_HAPPY = True
                        self.HAPPY_BUNDLE = params["bundle"]
                        return 1, self.get_bid()
                self.IS_HAPPY = True
                self.HAPPY_BUNDLE = params["bundle"]
                return 1, self.get_bid()
                # end ceca_purellm_f core step
            else:
                # begin xor elicitation proxy
                bundle = params["bundle"]
                
                prices = DirectPrices({
                    bundle: value
                    for bundle, value in self.manifest_valuation.atomic_bids
                })
            

                demanded_bundle: Bundle = self.person.Message(
                    "demand",
                    {
                        "prices": prices,
                        "bundle": bundle
                    }
                )
            
                if bundle == demanded_bundle:
                    return 1, self.get_bid()
                else:
                    demanded_bundle_value = self.person.Message(
                        "value",
                        {
                            "bundle": demanded_bundle
                        }
                    )

                    bundle_ = demanded_bundle.copy()

                    for item_type in demanded_bundle.scenario.item_types:
                        if bundle_.get_item_type_quantity(item_type) > 1:
                            bundle__ = bundle_.copy()

                            bundle__.set_item_type_quantity(item_type, 0)

                            if demanded_bundle_value >= self.person.Message(
                                "value",
                                {
                                    "bundle": bundle__
                                }):
                                logger.info("Removing item ", item_type)
                                bundle_ == bundle__
                            else:
                                logger.info("Keeping item ", item_type)


                    self.manifest_valuation.add_atomic_bid(
                        bundle_,
                        demanded_bundle_value
                    )

                    logger.info("Mainfest valuation return " + str(self.manifest_valuation))

                    return 0, self.get_bid()
                # end xor elicitation proxy


class CECA_HybridXOR_Proxy_Factory(ProxyFactory):

    def __init__(self,
                 check_priority: str,
                 target_bundle_priority: str,
                 happy_priority: str,
                 target_bundle_emphasis: str,
                 anchor_num_target_bundles: str,
                 cap: int,
                 min_iterations: int):
        self.check_priority = check_priority
        self.target_bundle_priority = target_bundle_priority
        self.happy_priority = happy_priority
        self.target_bundle_emphasis = target_bundle_emphasis
        self.anchor_num_target_bundles = anchor_num_target_bundles
        self.cap = cap
        self.min_iterations = min_iterations
 

    def __call__(self, person: Person) -> Proxy:
        return CECA_HybridXOR_Proxy(person,
                                    self.check_priority,
                                    self.target_bundle_priority,
                                    self.happy_priority,
                                    self.target_bundle_emphasis,
                                    self.anchor_num_target_bundles,
                                    CAP_INTERACTIONS = self.cap,
                                    MIN_ITERATIONS = self.min_iterations)
