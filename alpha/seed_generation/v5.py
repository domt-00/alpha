import json
import random
import re

from censusname import generate
from alpha.util import get_openai_client, retry
from alpha.person import SeedGenerationPipeline, Seed


@retry()
def get_bids(scenario):
    client = get_openai_client("openai")
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {
            "role": "user",
            "content": (
                "There is an auction that will run. Here is the inventory for auction:\n\n"
                + str(scenario)
                + "\n\nPlease help me come up with different people and different preferences for this auction. "
                  "Think through the specific purchase occasion and taste preferences for the occasion. "
                  "Write in present tense. Write a paragraph for each. Please give me three different people named: "
                + ", ".join([generate() for _ in range(3)])
                + "."
            ),
        },
    ]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "submit_response",
                "description": "Submit the response to the user's request. Please include multiple bidders as requested.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "number_of_bidders": {
                            "type": "integer",
                            "description": "The number of bidders to include in the response.",
                        },
                        "bidders": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "example_number": {
                                        "type": "integer",
                                        "description": "The number of the example.",
                                    },
                                    "name": {
                                        "type": "string",
                                        "description": "The name of a bidder.",
                                    },
                                    "description_of_preferences": {
                                        "type": "string",
                                        "description": "Here is the ideal customer profile's wishes for the current auction and other relevant information.",
                                    },
                                },
                                "required": [
                                    "example_number",
                                    "name",
                                    "description_of_preferences",
                                ],
                            },
                        },
                    },
                    "required": ["bidders"],
                },
            },
        }
    ]

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools,
        tool_choice="required",
        max_tokens=10000,
    )

    result = json.loads(completion.choices[0].message.tool_calls[0].function.arguments)["bidders"]

    entry = random.choice(result)

    return entry["description_of_preferences"], entry["name"]


@retry()
def revise_pref(pref, scenario):
    client = get_openai_client("openai")
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {
            "role": "user",
            "content": (
                "There is an auction that will run.\n\n"
                + str(scenario)
                + "\n\nHere is a description of a person's preferences for the auction:\n\n"
                + pref
                + "\n\nPlease help me identify discrepancies and areas lacking clarity. "
                  "Please also help identify opportunities to clarify the person's willingness to pay and how much "
                  "and what combinations of items they would want, e.g., one or another, one and/or another, one and another. "
                  "Then revise the description for this bidder so that they are more precise and accurate."
            ),
        },
    ]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "submit_response",
                "description": "Submit the response to the user's request. Please include multiple bidders as requested.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "wtp": {
                            "type": "string",
                            "description": "The person's background (career, family, etc.) and how it relates to their willingness to pay.",
                        },
                        "lacking_clarity_if_any": {
                            "type": "string",
                            "description": "Any areas lacking clarity in the description and the bidder string.",
                        },
                        "combination_info": {
                            "type": "string",
                            "description": "Any opportunities to clarify the person's willingness to pay and how much and what combinations of items they would want, e.g., one or another, one and/or another, one and another.",
                        },
                        "full_revised_preferences": {
                            "type": "string",
                            "description": "Here is the ideal customer profile's wishes for the current auction and other relevant information.",
                        },
                    },
                    "required": ["wtp", "full_revised_preferences"],
                },
            },
        }
    ]

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools,
        tool_choice="required",
        max_tokens=10000,
    )

    result = json.loads(completion.choices[0].message.tool_calls[0].function.arguments)

    return result["full_revised_preferences"]


@retry()
def elaborate_bid(bid, scenario):
    client = get_openai_client("openai")
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {
            "role": "user",
            "content": (
                "There is an auction that will run.\n\n"
                + str(scenario)
                + "\n\nHere is a current description of a person's preferences for the auction:\n\n"
                + bid
                + "\n\nPlease think through what the bidder said. Then consider things from a value perspective and what they value certain bundles at: "
                  "enumerate specific bundles with exact dollar values of each of the bundles. Valid bundles consist of either a single item or a combination of items in the scenario in the auction, including the item codes for each item in the bundle. "
                  "Considering the other items available, outline how willing the person will be to considering other bundles, and their criteria for considering substitutions or additional items. "
                  "Think in terms of value not budget. Summarize all of this into a clear, standalone, elaborated description of the preferences of the person with exact dollar values:\n\n"
                  "``` [ DESCRIPTION GOES HERE]```\n\n"
                  "Please write in third-person, e.g., Bob is ..., Alice values ... at ..., Charlie wants two of these and one of those, etc."
            ),
        },
    ]

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=10000,
        logit_bias={  # remove the word budget
            93338: -100,
            55743: -100,
            39770: -100,
            9946: -100,
            132556: -100
        },
    )

    result = completion.choices[0].message.content

    # Extract the content within the triple backticks
    result = re.search(r"```([^`]*)```", result).group(1)

    return result


@retry()
def refine_bid(elaborated_bid, scenario):
    """
    This function further refines the bidder's preferences by making them more precise,
    especially in evaluating complex bundles with multiple items.
    """
    client = get_openai_client("openai")
    
    messages = [
        {"role": "system", "content": "You are a meticulous assistant focused on precision."},
        {
            "role": "user",
            "content": (
                "Based on the following elaborated bidder preference description for an auction:\n\n"
                + elaborated_bid
                + "\n\n"
                "Please write a short statement on the process by the bidder evaluates complex bundles with many different items that will go at the end of the elaborated bidder preference description. Does the bidder view large bundles as additive in terms of their constituents? Does the bidder view large bundles as a necessity, e.g. they would be averse to accepting the constituents individually? Does the bidder value multiples of similar items additively or at a discounted rate and if so, how strong is the discount? Quantify how strongly these considerations matter in terms of percentage discounts, value of complementary, substitution, bulk effects."
                "Ensure that the evaluation process is clearly detailed and leaves no ambiguity about the bidder's decision-making."
            ),
        },
    ]

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=10000,
    )

    refined_result = completion.choices[0].message.content

    return elaborated_bid + refined_result


class SeedGenerationPipeline_v5(SeedGenerationPipeline):
    
    def __call__(cls, scenario):
        # Step 1: Generate initial bidder preferences
        pref, name = get_bids(scenario)
        
        # Step 2: Revise the preferences for clarity and accuracy
        bid = revise_pref(pref, scenario)
        
        # Step 3: Elaborate the bid with specific dollar values and bundle details
        bid = elaborate_bid(bid, scenario)
        
        # Step 4: Further refine the bid for precision in evaluating complex bundles
        bid = refine_bid(bid, scenario)
        
        return Seed(
            code=name.lower().replace(" ", ""), 
            scenario=scenario.code, 
            description=bid
        )
