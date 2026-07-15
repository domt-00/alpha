"""
NVD proxy with self-routing: before each question in the opening question phase,
the LLM decides whether it already has enough context to skip the question and
proceed directly to bundle valuation. This reduces unnecessary interactions when
the person's description is already informative enough.

Tracks `questions_asked` and `questions_skipped` for efficiency analysis.
"""

import re
from typing import Literal, Union

from pydantic import BaseModel, Field
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

from alpha.util import get_llm_client, get_llm_model, get_llm_provider, parse_structured_output, retry
from alpha.proxy import Proxy, ProxyFactory
from alpha.xor import XORBid
from alpha.auction import Auction, Allocation
from alpha.agent import Agent, MessageDecorator
from alpha.person import Person
from alpha.scenario import Scenario, DirectPrices, Bundle, scenario_empty_bundle, scenario_all_bundles

# ── Reuse structured output types from the original NVD ──────────────────────

from alpha.auctions.ceca_qllm_a import (
    describe_xorbid,
    TargetBundle,
    CheckPriceDemand,
    Happy,
    Action,
    InformationAction,
    BundleValue,
    CECA_QLLM_A_Proxy_Factory,   # factory base we'll override
)


class RoutingDecision(BaseModel):
    reasoning: str = Field(
        description="Brief reasoning about whether the person's description "
                    "and prior conversation already provide enough context to "
                    "estimate their bundle valuations."
    )
    decision: Literal["ASK", "SKIP"] = Field(
        description="ASK if another question is genuinely needed to understand "
                    "the person's preferences. SKIP if you already have enough "
                    "context to proceed with bundle valuation."
    )


class CECA_QLLM_A_SR_Proxy(Proxy):
    """
    NVD proxy with self-routing in the opening question phase.

    Before each of the first `num_questions` interactions the proxy asks itself:
    'Do I already know enough to skip this question?'  If yes, the question is
    skipped and the interaction budget is not wasted on a low-value query.
    """

    def __init__(self,
                 person: Person,
                 check_priority,
                 target_bundle_priority,
                 happy_priority,
                 target_bundle_emphasis,
                 anchor_num_target_bundles,
                 num_questions,
                 discount: float = 0.75,
                 CAP_INTERACTIONS: int = 20,
                 MIN_ITERATIONS: int = 0,
                 MAX_TRIES: int = 3,
                 compress_description: bool = False):
        self.person = person
        self.manifest_valuation = XORBid()
        self.MAX_TRIES = MAX_TRIES
        self.MIN_ITERATIONS = MIN_ITERATIONS
        self.CAP_INTERACTIONS = CAP_INTERACTIONS
        self.num_questions = num_questions
        self.discount = discount
        self.compress_description = compress_description
        self._compact_seed: str | None = None

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

        # Self-routing counters
        self.questions_asked = 0
        self.questions_skipped = 0

    def RealPerson(self) -> Person:
        return self.person

    def Support(self):
        return ["ceca_xor_step"]

    @retry()
    def _build_compact_seed(self) -> str:
        """One LLM call to compress the full person description into a compact WTP profile."""
        valid_codes = self.person.scenario.codes()
        messages = [{
            "role": "user",
            "content": (
                "Summarise this person's preferences for a combinatorial auction proxy. "
                "Max 150 words. Format exactly as:\n"
                "Person: [role, 1 line]\n"
                "Budget: [amount]\n"
                "WTP: " + " | ".join(f"[{c}]=$?" for c in valid_codes) + "\n"
                "(fill in each ? with the estimated willingness-to-pay)\n"
                "Rules: [key synergies, bundle rejections, diminishing returns — 1-3 lines]\n\n"
                "Full description:\n" + str(self.person.seed)
            )
        }]
        client = get_llm_client()
        response = client.chat.completions.create(
            model=get_llm_model(), messages=messages, max_tokens=300
        )
        return response.choices[0].message.content.strip()

    @property
    def _seed_text(self) -> str:
        """Return compact seed if compression enabled, otherwise full seed."""
        if not self.compress_description:
            return str(self.person.seed)
        if self._compact_seed is None:
            try:
                self._compact_seed = self._build_compact_seed()
            except Exception:
                self._compact_seed = str(self.person.seed)
        return self._compact_seed

    # ── Routing check ─────────────────────────────────────────────────────────

    @retry()
    def should_ask_question(self) -> bool:
        """
        Returns True if another question is needed, False if we can skip.
        A cheap single call that checks whether the existing description +
        conversation history is already sufficient for bundle valuation.
        """
        prior_qa = (
            "\n".join(["    " + x for x in self.conversation_history])
            if self.conversation_history
            else "    None yet."
        )

        messages = [
            {
                "role": "user",
                "content": (
                    "You are representing a person in a combinatorial auction. "
                    "You have already asked them "
                    f"{self.questions_asked} question(s) so far.\n\n"
                    "Scenario:\n" + self.person.scenario.Description() + "\n\n"
                    "Person's description:\n" + self._seed_text + "\n\n"
                    "Prior Q&A with the person:\n" + prior_qa + "\n\n"
                    "Available items: " + self.person.scenario.simple_item_overview() + "\n\n"
                    "Question: Do you know enough about this person's preferences "
                    "to bid accurately and competitively on their behalf RIGHT NOW, "
                    "without asking another question?\n"
                    "Be conservative: choose SKIP only if you can already estimate "
                    "their value for each relevant bundle with reasonable confidence. "
                    "Choose ASK if another question would materially improve your bid accuracy."
                )
            }
        ]

        client = get_llm_client()
        if get_llm_provider() == "ollama":
            messages[0]["content"]  # no extra_body needed for structured output

        routing = parse_structured_output(client, get_llm_model(), messages, RoutingDecision)
        return routing.decision == "ASK"

    # ── Value inference (identical to original NVD) ───────────────────────────

    @retry()
    def value_query(self, bundle: Bundle):
        messages = [
            {
                "role": "user",
                "content": (
                    "You helping to represent a person in a scenario where we are bidding on their behalf in an auction. "
                    "\n\n"
                    "Here is the scenario description: \n"
                    + self.person.scenario.Description()
                    + "\n\n"
                    "Here is the description of the person's preferences: \n"
                    + self._seed_text
                    + "\n\n"
                    "Here is the current conversation history with the person: \n"
                    + (
                        "\n".join(["    " + x for x in self.conversation_history])
                        if self.conversation_history
                        else "    No records available."
                    )
                    + (
                        "primary conversation: \n"
                        + "\n".join(["    " + x for x in self.primary_conversation_history])
                        if self.primary_conversation_history
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
        new_inferred_valuations = {}
        all_bundles = scenario_all_bundles(self.person.scenario)
        bundles_to_query = [
            bundle for bundle in all_bundles
            if not any(bundle == b2 for b2, _ in self.manifest_valuation.atomic_bids)
        ]

        max_workers = 1 if get_llm_provider() == "ollama" else (min(10, len(bundles_to_query)) if bundles_to_query else 1)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_bundle = {executor.submit(self.value_query, bundle): bundle for bundle in bundles_to_query}
            for future in tqdm(as_completed(future_to_bundle), total=len(future_to_bundle), desc="Refreshing Valuations"):
                bundle = future_to_bundle[future]
                try:
                    value = future.result()
                    new_inferred_valuations[bundle] = int(value * self.discount)
                except Exception:
                    pass

        self.inferred_valuations = new_inferred_valuations

    def get_bid(self):
        if (self.current_num_iterations < 4) or (self.current_num_iterations < 24 and self.current_num_iterations % 3 == 0) or not hasattr(self, "inferred_valuations"):
            self.refresh_inferred_valuations()

        out_bid = self.manifest_valuation.copy()
        for bundle, value in self.inferred_valuations.items():
            if not any(bundle == b2 for b2, _ in out_bid.atomic_bids):
                out_bid.add_atomic_bid(bundle, value)

        return out_bid

    @retry()
    def get_next_question(self):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": (
                    "You helping to represent a person in a scenario where we are bidding on their behalf in an auction. "
                    "\n\n"
                    "Here is the scenario description: \n"
                    + self.person.scenario.Description()
                    + "\n\n"
                    "Here is the current conversation history with the person: \n"
                    + (
                        "\n".join(["    " + x for x in self.conversation_history])
                        if self.conversation_history
                        else "    No records available."
                    )
                    + (
                        "primary conversation: \n"
                        + "\n".join(["    " + x for x in self.primary_conversation_history])
                        if self.primary_conversation_history
                        else "    No records available."
                    )
                    + "\n\n"
                    "Here is the description of the person's preferences: \n"
                    + self._seed_text
                    + "\n\n"
                    + 'What should the proxy ask the person next to better understand their preferences? Please make sure to get to dollar values, be strategic about what items or groups of items you ask about to maximize information. If you have a good idea of the bidders valuation in general, you can ask about specific bundles of items to better understand their preferences. Otherwise, ask a general question. Reason step by step. Give their next question -- only one -- in the following format: Question: "[question here]"'
                )
            },
        ]

        client = get_llm_client()
        kwargs = {"model": get_llm_model(), "messages": messages}
        if get_llm_provider() == "ollama":
            kwargs["extra_body"] = {"think": False}
        response = client.chat.completions.create(**kwargs)
        result = response.choices[0].message.content or ""
        match = re.search(r'Question: "(.*)"', result)
        if match:
            return match.group(1)
        return result.strip() or "What is your budget for these items?"

    # ── Main message handler ───────────────────────────────────────────────────

    @MessageDecorator(cache=False)
    def Message(self, message_type: str, params: any, logger=None):
        if message_type == "ceca_xor_step":
            self.current_num_iterations += 1

            if (self.IS_HAPPY and self.HAPPY_BUNDLE == params["bundle"]) or self.current_num_iterations > self.CAP_INTERACTIONS:
                return 1, self.get_bid()

            # ── Self-routing: question phase ──────────────────────────────────
            if self.current_num_iterations <= self.num_questions:
                # Always ask the first question to establish a baseline anchor,
                # then let the model decide whether further questions are needed.
                if self.current_num_iterations <= 1:
                    ask = True
                else:
                    ask = self.should_ask_question()
                if ask:
                    # Standard question path
                    question = self.get_next_question()
                    answer = self.person.Message("question", {"question": question})
                    self.conversation_history.append(f"Proxy: {question}")
                    self.conversation_history.append(f"Person: {answer}")
                    self.primary_conversation_history.append(f"Proxy: {question}")
                    self.primary_conversation_history.append(f"Person: {answer}")
                    self.questions_asked += 1
                    return 0, self.get_bid()
                else:
                    # Skip: LLM already has enough context — fall through to bidding
                    self.questions_skipped += 1
                    self.conversation_history.append(
                        f"[SR] Question {self.current_num_iterations} skipped — sufficient context from description."
                    )
                    # Fall through to bidding logic below

            # ── Bidding phase (identical to original NVD) ─────────────────────
            prices = params["prices"]
            bundle = params["bundle"]
            allocated_bundle_value = self.person.Message("value", {"bundle": bundle})
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
                            "\n\n"
                            "Here is the scenario description: \n"
                            + self.person.scenario.Description()
                            + "\n\n"
                            "Here is the description of the person's preferences: \n"
                            + self._seed_text
                            + "\n\n"
                            + "Here are the currently tracked bundles:\n"
                            + "\n".join([x.to_code_description() for x, _ in self.manifest_valuation.atomic_bids]) + "\n\n"
                            + "Here are the current prices: \n"
                            + prices.Description()
                            + "\n\n"
                            + "Here is their currently allocated bundle: " + bundle.Description()
                            + "\n\n"
                            "Here is your current conversation history: \n"
                            + (
                                "\n".join(["    " + x for x in self.conversation_history])
                                if self.conversation_history
                                else "    No records available."
                            )
                            + (
                                "primary conversation: \n"
                                + "\n".join(["    " + x for x in self.primary_conversation_history])
                                if self.primary_conversation_history
                                else "    No records available."
                            )
                            + "\n\n"
                            "Please help me identify a single bundle that the bidder might want to target to bid on. If there is no such additional bundle, just say that the bidder is happy. If you want to double-check with the bidder to see what you want, just say that too. "
                            + f"\n\nFirst let's take stock on how the bidder feels about their currently allocated bundle at current prices. If they have no currently allocated bundle or if there is no current prices it is just the start of the auction, be AGGRESSIVE in trying out target bundles. At other times, prioritize: {self.target_bundle_emphasis}. The current target bundles will be shown in conversation history: make sure you target at least {self.anchor_num_target_bundles} bundles before saying the bidder is HAPPY. You may or may not choose to CHECK their demand at the given prices. It's a good idea to do so if you feel like you are missing something. Place a {self.check_priority} priority on giving a CHECK response, a {self.target_bundle_priority} priority on giving a TARGET_BUNDLE response, and a {self.happy_priority} priority on giving a HAPPY response. You are a helpful assistant, so without giving a final response give your thinking below. {'SYSTEM NOTE - DO NOT GIVE A HAPPY RESPONSE YET, NOT ENOUGH INFORMATION USE CHECK OR TARGET_BUNDLE' if self.current_num_iterations <= self.MIN_ITERATIONS else ''}"
                        ),
                    }
                ]

                try:
                    client = get_llm_client()

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

                    action = parse_structured_output(client, get_llm_model(), messages, Action)
                    logger.info(action)

                    if action.response.type == "HAPPY" and self.current_num_iterations <= self.MIN_ITERATIONS:
                        action.response = CheckPriceDemand(type="CHECK")
                except Exception as e:
                    logger.info(f"LLM call failed on attempt {tries}: {e}")
                    continue

                if action.response.type == "CHECK":
                    demanded_bundle: Bundle = self.person.Message("demand", {"prices": prices, "bundle": bundle})
                    self.conversation_history.append(f'Proxy: """CHECK: At the following prices, what would you want? \n{prices.Description()}"""')
                    self.conversation_history.append(f'Person: """I want this bundle, {demanded_bundle.to_code_description()}"""')

                    query_bundle = demanded_bundle
                    query_bundle_value = self.person.Message("value", {"bundle": query_bundle})
                    self.conversation_history.append(f'Person: """I value it at {query_bundle_value}"""')

                    query_bundle_utility = query_bundle_value - prices(query_bundle)
                    self.conversation_history.append(
                        f'System: Current prices mean this bundle has utility {query_bundle_utility} = {query_bundle_value} - {prices(query_bundle)}; compare this to current allocated bundle utility {allocated_bundle_utility}'
                    )
                    logger.debug(self.conversation_history[-1])

                    if query_bundle_utility > allocated_bundle_utility:
                        self.manifest_valuation.add_atomic_bid(query_bundle, query_bundle_value)
                        return 0, self.get_bid()

                elif action.response.type == "TARGET_BUNDLE":
                    logger.info("TARGET BUNDLE")
                    try:
                        query_bundle = Bundle.from_types_quantities(
                            self.person.scenario,
                            action.response.item_type_codes,
                            action.response.item_quantities,
                        )
                    except Exception:
                        continue

                    self.conversation_history.append(f'Proxy: """TARGET BUNDLE: What do you value the following bundle at? \n{query_bundle.Description()}"""')

                    if any(query_bundle == b for b, _ in self.manifest_valuation.atomic_bids):
                        self.conversation_history.append('Person: """I have already given you a value for this bundle, skip"""')
                    else:
                        query_bundle_value = self.person.Message("value", {"bundle": query_bundle})
                        self.conversation_history.append(f'Person: """I value it at {query_bundle_value}"""')

                        query_bundle_utility = query_bundle_value - prices(query_bundle)
                        self.conversation_history.append(
                            f'System: Current prices mean this bundle has utility {query_bundle_utility} = {query_bundle_value} - {prices(query_bundle)}; compare this to current allocated bundle utility {allocated_bundle_utility}'
                        )
                        logger.debug(self.conversation_history[-1])

                        if query_bundle_utility > allocated_bundle_utility:
                            self.manifest_valuation.add_atomic_bid(query_bundle, query_bundle_value)
                            return 0, self.get_bid()
                else:
                    logger.info("HAPPY")
                    self.conversation_history.append("Proxy -> Auction: HAPPY")
                    self.IS_HAPPY = True
                    self.HAPPY_BUNDLE = params["bundle"]
                    return 1, self.get_bid()

            if self.current_num_iterations <= self.MIN_ITERATIONS:
                return 0, self.get_bid()
            self.IS_HAPPY = True
            self.HAPPY_BUNDLE = params["bundle"]
            return 1, self.get_bid()


class CECA_QLLM_A_SR_Proxy_Factory(ProxyFactory):

    def __init__(self,
                 check_priority: str,
                 target_bundle_priority: str,
                 happy_priority: str,
                 target_bundle_emphasis: str,
                 anchor_num_target_bundles: str,
                 num_questions: int,
                 cap: int,
                 min_iterations: int,
                 compress_description: bool = False):
        self.check_priority = check_priority
        self.target_bundle_priority = target_bundle_priority
        self.happy_priority = happy_priority
        self.target_bundle_emphasis = target_bundle_emphasis
        self.anchor_num_target_bundles = anchor_num_target_bundles
        self.num_questions = num_questions
        self.cap = cap
        self.min_iterations = min_iterations
        self.compress_description = compress_description

    def __call__(self, person: Person) -> Proxy:
        return CECA_QLLM_A_SR_Proxy(
            person,
            self.check_priority,
            self.target_bundle_priority,
            self.happy_priority,
            self.target_bundle_emphasis,
            self.anchor_num_target_bundles,
            self.num_questions,
            CAP_INTERACTIONS=self.cap,
            MIN_ITERATIONS=self.min_iterations,
            compress_description=self.compress_description,
        )
