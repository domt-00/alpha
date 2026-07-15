import json
import random
import re

from pydantic import BaseModel

from alpha.util import get_llm_client, get_llm_model, parse_structured_output, retry

# Replacement for the broken censusname package (incompatible with Python 3.13)
_FIRST = ["Alice", "Bob", "Charlie", "Diana", "Edward", "Fiona", "George",
          "Hannah", "Ivan", "Julia", "Kevin", "Laura", "Marcus", "Nina",
          "Oscar", "Paula", "Quinn", "Rachel", "Samuel", "Tara"]
_LAST  = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
          "Miller", "Davis", "Wilson", "Moore", "Taylor", "Anderson",
          "Thomas", "Jackson", "White", "Harris", "Martin", "Thompson"]

def generate() -> str:
    return f"{random.choice(_FIRST)} {random.choice(_LAST)}"

from alpha.person import SeedGenerationPipeline, Seed


# ── Pydantic models for JSON-mode structured outputs ──────────────────────────

class BidderEntry(BaseModel):
    example_number: int
    name: str
    description_of_preferences: str

class BiddersResponse(BaseModel):
    bidders: list[BidderEntry]

class RevisedPreferences(BaseModel):
    wtp: str
    full_revised_preferences: str


# ── Pipeline steps ─────────────────────────────────────────────────────────────

@retry()
def get_bids(scenario):
    client = get_llm_client()
    model  = get_llm_model()

    names = ", ".join([generate() for _ in range(3)])

    messages = [
        {"role": "system", "content": "You are a helpful assistant. Always respond with valid JSON."},
        {
            "role": "user",
            "content": (
                "There is an auction that will run. Here is the inventory for auction:\n\n"
                + str(scenario)
                + "\n\nPlease help me come up with different people and different preferences for this auction. "
                  "Think through the specific purchase occasion and taste preferences for the occasion. "
                  "Write in present tense. Write a paragraph for each. Please give me three different people named: "
                + names
                + ".\n\n"
                  "Respond ONLY with a JSON object matching this schema:\n"
                  '{"bidders": [{"example_number": <int>, "name": "<str>", "description_of_preferences": "<str>"}, ...]}'
            ),
        },
    ]

    result = parse_structured_output(client, model, messages, BiddersResponse)
    entry = random.choice(result.bidders)
    return entry.description_of_preferences, entry.name


@retry()
def revise_pref(pref, scenario):
    client = get_llm_client()
    model  = get_llm_model()

    messages = [
        {"role": "system", "content": "You are a helpful assistant. Always respond with valid JSON."},
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
                  "Then revise the description for this bidder so that they are more precise and accurate.\n\n"
                  "Respond ONLY with a JSON object matching this schema:\n"
                  '{"wtp": "<background and WTP info>", "full_revised_preferences": "<revised description>"}'
            ),
        },
    ]

    result = parse_structured_output(client, model, messages, RevisedPreferences)
    return result.full_revised_preferences


@retry()
def elaborate_bid(bid, scenario):
    client = get_llm_client()

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
        model=get_llm_model(),
        messages=messages,
        max_tokens=1500,
    )

    result = completion.choices[0].message.content

    # Extract the content within the triple backticks
    match = re.search(r"```([^`]*)```", result)
    if match:
        return match.group(1)
    return result  # fall back to full response if no backtick block found


@retry()
def refine_bid(elaborated_bid, scenario):
    """
    Further refines the bidder's preferences by making them more precise,
    especially in evaluating complex bundles with multiple items.
    """
    client = get_llm_client()

    messages = [
        {"role": "system", "content": "You are a meticulous assistant focused on precision."},
        {
            "role": "user",
            "content": (
                "Based on the following elaborated bidder preference description for an auction:\n\n"
                + elaborated_bid
                + "\n\n"
                "Please write a short statement on the process by which the bidder evaluates complex bundles with many different items that will go at the end of the elaborated bidder preference description. "
                "Does the bidder view large bundles as additive in terms of their constituents? "
                "Does the bidder view large bundles as a necessity, e.g. they would be averse to accepting the constituents individually? "
                "Does the bidder value multiples of similar items additively or at a discounted rate and if so, how strong is the discount? "
                "Quantify how strongly these considerations matter in terms of percentage discounts, value of complementary, substitution, bulk effects. "
                "Ensure that the evaluation process is clearly detailed and leaves no ambiguity about the bidder's decision-making."
            ),
        },
    ]

    completion = client.chat.completions.create(
        model=get_llm_model(),
        messages=messages,
        max_tokens=1500,
    )

    refined_result = completion.choices[0].message.content
    return elaborated_bid + refined_result


class SeedGenerationPipeline_v5(SeedGenerationPipeline):

    def __init__(self, num_steps=4):
        self.num_steps = num_steps

    def __call__(self, scenario):
        # Step 1: Generate initial bidder preferences
        pref, name = get_bids(scenario)
        bid = pref

        # Step 2: Revise the preferences for clarity and accuracy
        if self.num_steps >= 2:
            bid = revise_pref(pref, scenario)

        # Step 3: Elaborate the bid with specific dollar values and bundle details
        if self.num_steps >= 3:
            bid = elaborate_bid(bid, scenario)

        # Step 4: Further refine the bid for precision in evaluating complex bundles
        if self.num_steps >= 4:
            bid = refine_bid(bid, scenario)

        return Seed(
            code=name.lower().replace(" ", ""),
            scenario=scenario.code,
            description=bid
        )
