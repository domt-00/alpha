import re
import json
import os
import random

from alpha.person import (
    QuestionPipeline,
    EquivalencePipeline,
    ValuePipeline,
    value_decorator,
    Seed,
)
from alpha.scenario import Scenario, Bundle, Prices, scenario_empty_bundle
from alpha.util import get_openai_client
from alpha.person import Person
from alpha.agent import Agent, MessageDecorator
from alpha.util import retry, get_openai_client

from pydantic import BaseModel, Field
from typing import Literal, Union

value_statement = """

Please always use the following five-step process whenever estimating a person's value for a given bundle given their preferences:
    1. Check if the person has explicitly stated the value for that bundle, give this if so
    2. Find the closest bundle(s) from the given bundle that the person has explicitly valued
    3. Identify the process by which the person has specified they will calculate their value
    4. Identify any other relevant criteria
    5. Factor (2), (3), and (4) in to estimate the person's value

"""


class BundleModel(BaseModel):
    reasoning: str = Field(description="Reasoning for giving this bundle")
    ensure_no_duplication: str = Field(description="Check to ensure it's not duplicating another bundle")
    bundle_idx: int = Field(description="index of bundle in list. N/5")
    item_type_codes: list[str] = Field(
        description="A list of codes identifying the item type. Only give each item type code once. For multiples of the same item, indicate it in item_quantities."
    )
    item_quantities: list[int] = Field(
        description="A list of quantities identify the amount of the corresponding item type. Ensure that the item quantity here is less than or equal to the total quantity available"
    )
    
class NotEquivalent(BaseModel):
    type: Literal["NOT EQUIVALENT"] = Field(description="NOT EQUIVALENT")
    reasoning: str = Field(
        description="Process and criteria for choosing the list of bundles"
    )
    bundles: list[BundleModel] = Field(description="The list of bundles, up to 5 bundles.")
    
class Equivalent(BaseModel):
    type: Literal["EQUIVALENT"] = Field(description="EQUIVALENT")
    reasoning: str = Field(description="Reasoning for saying its EQUIVALENT")
    

class EquivalenceResponse(BaseModel):
    response: Union[NotEquivalent, Equivalent] = Field(description="response")

class StandardQuestionPipeline(QuestionPipeline):
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.params = model

    def __call__(
        self, scenario: Scenario = None, seed: Seed = None, question: str = None, logger = None
    ) -> float:
        """
        Queries the value associated with a question for a given scenario and seed.
        Utilizes a CSV cache to store and retrieve previous query results.

        Parameters:
        - scenario: An object with a 'code' attribute representing the scenario.
        - seed: An object with a 'code' attribute representing the seed.
        - question: The question string to query.
        - flag: An optional flag to differentiate queries.

        Returns:
        - The answer to the question as a string.
        """
        
        assert scenario is not None, "scenario cannot be None for StandardQuestionPipeline"
        assert seed is not None, "seed cannot be None for StandardQuestionPipeline"
        assert question is not None, "question cannot be None for StandardQuestionPipeline"

        if "gpt" in self.model:
            client = get_openai_client("openai")
        else:
            client = get_openai_client("google")

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "system",
                "content": (
                    f"Here is the scenario description: {scenario}.\n\n"
                    f"Here is the description of a person who is interested in making a bid in this auction: {seed}.\n\n"
                    "*****\n"
                    f"The person is asked the following question: {question}\n"
                    "*****\n\n"
                    "Please reason through and then craft how you think the person would respond to the question. "
                    "Keep the answer concise (only one sentences) and relevant to the question. "
                    'Provide the answer in the following format: ```Answer: "[response]"```.'
                ),
            },
        ]

        try:
            completion = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=1000,
            )
        except Exception as e:
            return "Error: Unable to fetch answer."

        content = completion.choices[0].message.content

        # Extract the answer using regex
        match = re.search(r'```Answer: "(.*)"```', content, re.DOTALL)

        if match:
            answer = match.group(1).strip()
        else:
            answer = "Unable to determine the answer."

        return answer


class StandardValuePipeline(ValuePipeline):
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.params = model

    @value_decorator
    @retry()
    def __call__(
        self,
        scenario: Scenario = None,
        seed: Seed = None,
        bundle: Bundle = None,
        use_cache: bool = False,
        flag: int = 0,
        logger = None,
    ) -> float:
        
        assert scenario is not None, "scenario cannot be None for StandardValuePipeline"
        assert seed is not None, "seed cannot be None for StandardValuePipeline"
        assert bundle is not None, "bundle cannot be None for StandardValuePipeline"
        
        if bundle.total_quantity() == 0:
            return 0

        if "gpt" in self.model:
            client = get_openai_client("openai")
        else:
            client = get_openai_client("google")

        messages = [
            {
                "role": "user",
                "content": "Here is the scenario description: "
                + str(scenario)
                + ".\n\nHere is the description of a person's preferences who is interested in making a bid in this auction: "
                + str(seed)
                + ".\n\n*****\n They have the option to receive the following PROPOSED_BUNDLE of items: \n"
                + bundle.to_code_description()
                + ". *****\ \n\nPlease give what you think the person would value this PROPOSED_BUNDLE of items at. " 
                + value_statement 
                + "Give the final value of the bundle of the "
                + str(bundle.total_quantity())
                + " items in the following format: ```Bundle value: $[value]```.",
            }
        ]

        completion = client.chat.completions.create(
            model=self.model,
            messages=messages,
        )

        content = completion.choices[0].message.content
        
        # Extract the value using regex
        match = re.search(r"Bundle value: \$([0-9,]+(?:\.[0-9]+)?)`", content)

        if match:
            value_str = match.group(1).replace(",", "")
            value = float(value_str)
        else:
            match = re.search(r"Bundle value: \$([0-9,]+(?:\.[0-9]+)?)\*", content)

            if match:
                value_str = match.group(1).replace(",", "")
                value = float(value_str)
            else:
                raise ValueError("Failed to extract value from API response.")
        return value

class StandardValuePipeline2(ValuePipeline):
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.params = model

    @value_decorator
    @retry()
    def __call__(
        self,
        scenario: Scenario = None,
        seed: Seed = None,
        bundle: Bundle = None,
        use_cache: bool = False,
        flag: int = 0,
        logger = None,
    ) -> float:
        
        assert scenario is not None, "scenario cannot be None for StandardValuePipeline"
        assert seed is not None, "seed cannot be None for StandardValuePipeline"
        assert bundle is not None, "bundle cannot be None for StandardValuePipeline"
        
        if bundle.total_quantity() == 0:
            return 0

        import openai

        client = openai.OpenAI(
          base_url="https://openrouter.ai/api/v1",
          api_key=os.environ["OPENROUTER_API_KEY"],
        )

        messages = [
            {
                "role": "user",
                "content": "Here is the scenario description: "
                + str(scenario)
                + ".\n\nHere is the description of a person's preferences who is interested in making a bid in this auction: "
                + str(seed)
                + ".\n\n*****\n They have the option to receive the following PROPOSED_BUNDLE of items: \n"
                + bundle.to_code_description()
                + ". *****\ \n\nPlease give what you think the person would value this PROPOSED_BUNDLE of items at. " 
                + value_statement 
                + "Give the final value of the bundle of the "
                + str(bundle.total_quantity())
                + " items in the following format: ```Bundle value: $[value]```.",
            }
        ]

        completion = client.chat.completions.create(
            model=self.model,
            messages=messages,
        )

        content = completion.choices[0].message.content
        
        # Extract the value using regex
        match = re.search(r"Bundle value: \$([0-9,]+(?:\.[0-9]+)?)`", content)

        if match:
            value_str = match.group(1).replace(",", "")
            value = float(value_str)
        else:
            match = re.search(r"Bundle value: \$([0-9,]+(?:\.[0-9]+)?)\*", content)

            if match:
                value_str = match.group(1).replace(",", "")
                value = float(value_str)
            else:
                raise ValueError("Failed to extract value from API response.")
        return value

class StandardEquivalencePipeline(EquivalencePipeline):
    def __init__(self, epsilon = "10%", model: str = "gpt-4o-mini"):
        self.model = model
        self.params = model
        self.num_calls = 1
        self.epsilon = epsilon

    @retry()
    def __call__(
        self,
        scenario: Scenario = None,
        seed: Seed = None,
        atomic_bids: list[Bundle, int] = None,
        values: list[Bundle, int] = None,
        logger = None
    ) -> Bundle:
        
        assert scenario is not None, "scenario cannot be None for StandardEquivalencePipeline"
        assert seed is not None, "seed cannot be None for StandardEquivalencePipeline"
        assert atomic_bids is not None, "prices cannot be None for StandardEquivalencePipeline"
        
        if "google" not in self.model.lower():
            client = get_openai_client("openai")
        else:
            client = get_openai_client("google")

        # Updated prompt to allow specifying quantities with ITEM_CODExN
        messages = [
            {
                "role": "user",
                "content": (
                    "Here is the scenario description: " + str(scenario)
                    + ".\n\nHere is the description of the person's preferences. The person is interested in making a bid in this auction: "
                    + seed.Description()
                    + """ An XOR preference $\\theta = (B, v)$ consists of a set of atomic bundles $B \subseteq \mathcal{B}$ and valuation function $v: B \\rightarrow \mathbb{R}_+$. For any bundle $b \in \mathcal{B}$, this preference $\\theta$ induces the valuation
\[
v^*(b) = \max_{{\{b' \in B \mid b' \subseteq b\}}} v(b')
\]
This formulation captures the idea that the value of a bundle is determined by the highest-valued atomic bundle it contains. Similarly, prices $\phi$ induce prices $\phi^*$, where the price of a bundle is the highest price of a bundle it contains. The induced valuations and prices capture the notion of  $\\textit{free disposal}$, i.e., the price or valuation of a bundle do not increase when an item in the bundle is removed. """ 
                    + "\n\nHere the hypothesis XOR valuation function as a list of atomic bids: \n" 
                    + ("\n".join([
                        f"[[[[ Atomic bid {j+1} - Bundle: " + entry[0].to_code_description() + "; Valued at " + str(entry[1]) + "]]]]"  for j, entry in enumerate(atomic_bids)
                    ]) if len(atomic_bids) > 0 else "* there are currently no atomic bids *\n" )
                    + value_statement 
                    + "The person has have explicitly valued the following bundles: \n"
                    + ("\n".join([
                        "[[[[ Bundle: " + entry[0].to_code_description() + "; Valued at " + str(entry[1]) + "]]]]"  for j, entry in enumerate(values)
                    ]))
                    + f"\n\nPlease help me identify which the bundles, if any, where the hypothesis XOR valuation function would be the most incorrect in relation to the person's own valuation from their explicit valuation of the bundles and secondarily the description of the person's preferences. Ignore those that are less than {self.epsilon} off. Ask these key questions to make sure we don't miss anything: \n\n"
                    + """1. What items have not been mentioned that the person would have a valuation over? What is the implicit valuation of items not mentioned explicitly by the person?
2. What bundles of items does the person have specific interest in?
3. Would the person accept modifications to those bundles? If so, what?
4. What about larger bundles that have all or nearly all of the items, or multiple sub-bundles of interest?
5. Choose a random bundle (flip a coin for each item) and see if it should be included\n\n"""
                    + f"This is call number {self.num_calls} of an iterative process to elicit their full XOR valuation. Bundles can have one or many items. A bundle can have all or nearly all of the items. Please give the item types codes and quantities to represent a bundle bundle. Give me five bundles if NOT EQUIVALENT if possible. DO NOT GIVE BUNDLES ALREADY IN THE XOR VALUATION.Valid item type codes: {', '.join(scenario.codes())}"
                ),
            }
        ]
        
        
        completion = client.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=EquivalenceResponse
        )
        response_object = completion.choices[0].message.parsed
        
        if response_object.response.type == "EQUIVALENT":
            self.num_calls += 1
            return 1, None
        else:
            
            bundles = []
            for bundle_model in response_object.response.bundles:
                quantities = [0 for i in range(len(scenario))]
            
                for item_type_code, quantity in zip(
                    bundle_model.item_type_codes, bundle_model.item_quantities
                ):
                    if item_type_code in scenario.codes():
                        idx = scenario.codes().index(item_type_code)
                        quantities[idx] = quantity

                bundle = Bundle(scenario=scenario, quantities=quantities)
                
                if not any([bundle == bundle_ for bundle_, v in atomic_bids]) and sum(quantities) > 0:
                    bundles.append(bundle)
                    
            if len(bundles) == 0:
                return 1, None
            
            bundle = random.choice(bundles)
            
            self.num_calls += 1
            return 0, bundle

class StandardPerson(Person):
    """
    Standard person to use for evaluating against
    """
    
    def __init__(
        self,
        scenario: Scenario,
        seed: Seed,
    ):
        self.scenario = scenario
        self.seed = seed
        self.value_pipeline = StandardValuePipeline()
        self.question_pipeline = StandardQuestionPipeline()
        self.demand_pipeline = StandardEquivalencePipeline()
        self.context = {}

    @MessageDecorator(cache = True)
    def Message(self, message_type: str, params: any, logger = None):
        assert (
            message_type in self.Support()
        ), f"Message type '{message_type}' is not supported, please give one of the supported message types: {', '.join(self.Support())}"

        if message_type == "question":
            return self.question_pipeline(
                scenario=self.scenario, seed=self.seed, question=params["question"], logger = logger
            )
        elif message_type == "value":
            return self.value_pipeline(
                scenario=self.scenario,
                seed=self.seed,
                bundle=params["bundle"],
                use_cache=params["use_cache"] if "use_cache" in params else False,
                flag=params["flag"] if "flag" in params else 0,
                logger = logger
            )
        elif message_type == "demand":
            return self.demand_pipeline(
                scenario=self.scenario,
                seed=self.seed,
                prices=params["prices"],
                bundle=params["bundle"],
                logger = logger
            )
