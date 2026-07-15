from ortools.linear_solver import pywraplp
from tqdm import tqdm
from typing import Union, Literal

from pydantic import BaseModel, Field

from alpha.util import get_llm_client, get_llm_model, get_llm_provider, parse_structured_output, retry
from alpha.proxy import Proxy, ProxyFactory
from alpha.xor import XORBid
from alpha.auction import Auction, Allocation
from alpha.agent import Agent, MessageDecorator
from alpha.person import Person
from alpha.scenario import Scenario, DirectPrices, Bundle, scenario_empty_bundle

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



class CECA_PureLLM_G_Proxy(Proxy):
    def __init__(self, 
                 person: Person, 
                 check_priority,
                 target_bundle_priority,
                 happy_priority,
                 target_bundle_emphasis,
                 anchor_num_target_bundles,
                 discount: float = 0.75,
                 CAP_INTERACTIONS: int = 20,
                 MIN_ITERATIONS: int = 0,
                 MAX_TRIES: int = 3):
        self.person = person
        self.manifest_valuation = XORBid()
        self.discount = discount
        self.MAX_TRIES = MAX_TRIES
        self.MIN_ITERATIONS = MIN_ITERATIONS
        self.CAP_INTERACTIONS = CAP_INTERACTIONS
        self.conversation_history = []
        
        self.HAPPY_BUNDLE = None
        self.IS_HAPPY = False
        
        self.check_priority = check_priority
        self.target_bundle_priority = target_bundle_priority
        self.happy_priority = happy_priority
        self.target_bundle_emphasis = target_bundle_emphasis
        self.anchor_num_target_bundles = anchor_num_target_bundles
        
        self.current_num_iterations = 0

    def RealPerson(self) -> Person:
        return self.person

    def Support(self):
        return ["ceca_xor_step"]

    @MessageDecorator(cache=True)
    def Message(self, message_type: str, params: any, logger=None):
        if message_type == "ceca_xor_step":
            
            self.current_num_iterations += 1
            
            if (self.IS_HAPPY and self.HAPPY_BUNDLE == params["bundle"]) or self.NumberOfHumanInteractions() > self.CAP_INTERACTIONS:
                return 1, self.manifest_valuation
            prices = params["prices"]
            bundle = params["bundle"]
            
            allocated_bundle_utility = self.person.Message(
                "value",
                {
                    "bundle": bundle
                }
            ) - prices(bundle)
            
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
                            "Here is the description of the person's preferences: \n"
                            + str(self.person.seed)
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
                            "Please help me identify a single bundle that the bidder might want to target to bid on. If there is no such additional bundle, just say that the bidder is happy. If you want to double-check with the bidder to see what they want, just say that too. "
                            + f"\n\nFirst let's take stock on how the bidder feels about their currently allocated bundle at current prices. If they have no currently allocated bundle or if there is no current prices it is just the start of the auction, be AGGRESSIVE in trying out target bundles. At other times, prioritize: {self.target_bundle_emphasis}. The current target bundles will be shown in conversation history: make sure you target at least {self.anchor_num_target_bundles} bundles before saying the bidder is HAPPY. You may or may not choose to CHECK their demand at the given prices. It's a good idea to do so if you feel like you are missing something. Place a {self.check_priority} priority on giving a CHECK response, a {self.target_bundle_priority} priority on giving a TARGET_BUNDLE response, and a {self.happy_priority} priority on giving a HAPPY response. You are a helpful assistant, so without giving a final response give your thinking below. {'SYSTEM NOTE - DO NOT GIVE A HAPPY RESPONSE YET, NOT ENOUGH INFORMATION USE CHECK OR TARGET_BUNDLE' if self.current_num_iterations <= self.MIN_ITERATIONS else ''}"
                        ),
                    }
                ]
                
                try:
                    client = get_llm_client()

                    # For slow local models skip the thinking call — Gemma uses the thinking
                    # output to convince itself to say HAPPY, then fails InformationAction parse.
                    if get_llm_provider() != "ollama":
                        @retry(max_delay=60)
                        def _thinking_call():
                            return client.chat.completions.create(
                                model=get_llm_model(), messages=messages
                            )
                        completion = _thinking_call()
                        messages.append(completion.choices[0].message)
                        messages.append({"role": "user", "content": "Now format to give the appropriate action of either TARGET_BUNDLE, CHECK, or HAPPY. Do not target a bundle already targetted. Here are the items and their quantities available. Do not give a bundle exceeding the available quantities " + self.person.scenario.simple_item_overview()})
                    else:
                        early = self.current_num_iterations <= self.MIN_ITERATIONS
                        messages[0]["content"] += (
                            "\n\nYou MUST respond with TARGET_BUNDLE or CHECK — do NOT choose HAPPY yet, you have not explored enough bundles. Do not target a bundle already targetted. Available items: "
                            + self.person.scenario.simple_item_overview()
                            if early else
                            "\n\nNow choose: TARGET_BUNDLE, CHECK, or HAPPY. Do not target a bundle already targetted. Available items: "
                            + self.person.scenario.simple_item_overview()
                        )

                    logger.info(messages)

                    action = parse_structured_output(
                        client,
                        get_llm_model(),
                        messages,
                        Action,
                    )
                    logger.info(action)

                    # If Gemma says HAPPY too early, treat it as a CHECK instead.
                    if action.response.type == "HAPPY" and self.current_num_iterations <= self.MIN_ITERATIONS:
                        action.response = CheckPriceDemand(type="CHECK")
                except Exception as e:
                    logger.info(f"LLM call failed on attempt {tries}: {e}")
                    continue

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
                        return 0, self.manifest_valuation
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
                            return 0, self.manifest_valuation
                else:
                    logger.info("HAPPY")
                    self.conversation_history.append(
                        "Proxy -> Auction: HAPPY"
                    )
                    self.IS_HAPPY = True
                    self.HAPPY_BUNDLE = params["bundle"]
                    return 1, self.manifest_valuation
            self.IS_HAPPY = True
            self.HAPPY_BUNDLE = params["bundle"]
            return 1, self.manifest_valuation


class CECA_PureLLM_G_Proxy_Factory(ProxyFactory):

    def __init__(self,
                 check_priority: str,
                 target_bundle_priority: str,
                 happy_priority: str,
                 target_bundle_emphasis: str,
                 anchor_num_target_bundles: str,
                 cap: int,
                 min_iterations: int,
                 discount: float = 0.75):
        self.check_priority = check_priority
        self.target_bundle_priority = target_bundle_priority
        self.happy_priority = happy_priority
        self.target_bundle_emphasis = target_bundle_emphasis
        self.anchor_num_target_bundles = anchor_num_target_bundles
        self.cap = cap
        self.min_iterations = min_iterations
        self.discount = discount


    def __call__(self, person: Person) -> Proxy:
        return CECA_PureLLM_G_Proxy(person,
                                    self.check_priority,
                                    self.target_bundle_priority,
                                    self.happy_priority,
                                    self.target_bundle_emphasis,
                                    self.anchor_num_target_bundles,
                                    discount=self.discount,
                                    CAP_INTERACTIONS=self.cap,
                                    MIN_ITERATIONS=self.min_iterations)
