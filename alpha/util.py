import itertools
import threading
import logging
import random
import os
import time
import traceback
import inspect
import json
import re
import csv
from functools import wraps
from datetime import datetime

import openai


# ---------------------------------------------------------------------------
# Token usage tracker
# ---------------------------------------------------------------------------

class _TokenTracker:
    """Thread-safe global token usage counter. Writes a CSV row per API call."""

    def __init__(self):
        self._lock = threading.Lock()
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self._csv_path = None
        self._benchmark = "unknown"
        self._stage = "unknown"

    def set_context(self, benchmark: str = "", stage: str = ""):
        """Call at the start of each script to tag subsequent token rows."""
        with self._lock:
            self._benchmark = benchmark or "unknown"
            self._stage = stage or "unknown"

    def _ensure_csv(self):
        if self._csv_path:
            return
        os.makedirs("logs", exist_ok=True)
        self._csv_path = "logs/token-usage.csv"
        if not os.path.exists(self._csv_path):
            with open(self._csv_path, "w", newline="") as f:
                csv.writer(f).writerow([
                    "timestamp", "provider", "model", "benchmark", "stage",
                    "prompt_tokens", "completion_tokens", "total_tokens", "cost_usd",
                ])

    def add(self, usage, model: str = ""):
        if usage is None:
            return
        pt = getattr(usage, "prompt_tokens", 0) or 0
        ct = getattr(usage, "completion_tokens", 0) or 0
        tt = getattr(usage, "total_tokens", 0) or (pt + ct)
        pricing = PRICING_PER_TOKEN.get(model, {"input": 0.0, "output": 0.0})
        cost = round(pt * pricing["input"] + ct * pricing["output"], 8)
        with self._lock:
            self.calls += 1
            self.prompt_tokens += pt
            self.completion_tokens += ct
            self.total_tokens += tt
            try:
                self._ensure_csv()
                provider = os.getenv("LLM_PROVIDER", "unknown")
                with open(self._csv_path, "a", newline="") as f:
                    csv.writer(f).writerow([
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        provider, model, self._benchmark, self._stage,
                        pt, ct, tt, cost,
                    ])
            except Exception:
                pass

    def summary(self) -> str:
        return (
            f"API calls: {self.calls} | "
            f"prompt tokens: {self.prompt_tokens:,} | "
            f"completion tokens: {self.completion_tokens:,} | "
            f"total tokens: {self.total_tokens:,}"
        )


token_tracker = _TokenTracker()


def generate_binary_lists(N, M):
    # Generate combinations of indices where the 1s will be placed
    indices = itertools.combinations(range(N), M)

    # Generate the binary lists based on the combinations of indices
    binary_lists = []
    for combo in indices:
        # Start with a list of all 0s
        binary_list = [0] * N
        # Set the indices in the combination to 1
        for index in combo:
            binary_list[index] = 1
        binary_lists.append(binary_list)

    return binary_lists


def retry(max_attempts=20, delay=1, expansion=2, use_default=False, default=None, exceptions=(Exception,), max_delay=60):
    """
    A decorator that retries a function call if an exception is raised.

    Parameters:
    - max_attempts: The maximum number of retry attempts.
    - delay: The initial delay (in seconds) between retries.
    - expansion: The factor by which the delay increases after each attempt.
    - use_default: If True, returns the default value upon failure instead of raising the exception.
    - default: The default value to return if use_default is True.
    - exceptions: A tuple of exception classes to catch and retry upon.
    - max_delay: Cap on backoff delay in seconds (default 60) to prevent multi-hour waits.

    Returns:
    - The result of the function if successful, otherwise the default value or raises the exception.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay + random.random()
            attempt = 0
            while attempt < max_attempts:
                try:
                    # Retrieve and print the function signature with arguments
                    func_signature = inspect.signature(func)
                    bound_arguments = func_signature.bind(*args, **kwargs)
                    bound_arguments.apply_defaults()

                    return func(*args, **kwargs)
                except exceptions as e:
                    attempt += 1
                    print(f"Attempt {attempt} of {max_attempts} for {func.__name__} failed with error: {e}")

                    # Print the full traceback
                    print("Traceback details:")
                    traceback.print_exc()

                    # Daily quota exhausted — no point retrying, re-raise immediately.
                    # Per-minute limits (token_quota_exceeded without "per day") do recover — let retry handle them.
                    err_str = str(e)
                    if "Tokens per day limit exceeded" in err_str:
                        print("Daily token quota exceeded — skipping retries.")
                        raise

                    if attempt < max_attempts:
                        wait = min(current_delay, max_delay)
                        print(f"Retrying in {wait:.2f} seconds...\n")
                        time.sleep(wait)
                        current_delay *= expansion
                    else:
                        print("Max retries reached. Handling failure.")
                        if use_default:
                            print(f"Returning default value: {default}")
                            return default
                        else:
                            print("Raising the exception.")
                            raise
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# LLM provider configuration
# ---------------------------------------------------------------------------
# Configure your provider in the .env file:
#
#   LLM_PROVIDER=groq          # or "mistral" (default: groq)
#   LLM_MODEL=llama-3.3-70b-versatile   # optional override
#   GROQ_API_KEY=gsk_...       # required when LLM_PROVIDER=groq
#   MISTRAL_API_KEY=...        # required when LLM_PROVIDER=mistral
# ---------------------------------------------------------------------------

PROVIDER_CONFIGS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "api_key_env": "MISTRAL_API_KEY",
        "default_model": "mistral-small-latest",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "api_key_env": None,
        "default_model": "gemma4:12b",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "default_model": "gemini-2.0-flash",
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "api_key_env": "CEREBRAS_API_KEY",
        "default_model": "gpt-oss-120b",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
    },
}

# USD per token (input, output). Used for cost estimation in logs.
PRICING_PER_TOKEN = {
    "deepseek-chat":     {"input": 0.27e-6, "output": 1.10e-6},
    "deepseek-reasoner": {"input": 0.55e-6, "output": 2.19e-6},
    "gemini-2.0-flash":  {"input": 0.075e-6, "output": 0.30e-6},
    "mistral-small-latest": {"input": 0.10e-6, "output": 0.30e-6},
    "mistral-medium-latest": {"input": 0.40e-6, "output": 2.00e-6},
    "mistral-large-latest": {"input": 2.00e-6, "output": 6.00e-6},
    # Local / free-tier providers — cost is $0
    "gpt-oss-120b": {"input": 0.0, "output": 0.0},
    "gemma4:12b":   {"input": 0.0, "output": 0.0},
}


def get_llm_provider() -> str:
    return os.getenv("LLM_PROVIDER", "groq").lower()


def get_llm_model() -> str:
    """Return the model name to use, respecting LLM_MODEL env override."""
    provider = get_llm_provider()
    default = PROVIDER_CONFIGS[provider]["default_model"]
    return os.getenv("LLM_MODEL", default)


def get_llm_client() -> openai.OpenAI:
    """
    Return an OpenAI-compatible client for the configured LLM provider.
    Groq, Mistral, and Ollama all expose an OpenAI-compatible REST API.
    """
    provider = get_llm_provider()
    if provider not in PROVIDER_CONFIGS:
        raise ValueError(
            f"Unknown LLM_PROVIDER='{provider}'. Valid options: {list(PROVIDER_CONFIGS.keys())}"
        )
    config = PROVIDER_CONFIGS[provider]
    if config["api_key_env"] is None:
        api_key = "ollama"
    else:
        api_key = os.environ.get(config["api_key_env"])
        if not api_key:
            raise EnvironmentError(
                f"API key not found. Please set {config['api_key_env']} in your .env file."
            )
    # Local providers (Ollama) can be slow; 900s allows Gemma 12B to finish long thinking responses.
    timeout = 900 if provider == "ollama" else 60
    return openai.OpenAI(base_url=config["base_url"], api_key=api_key, timeout=timeout)


def get_openai_client(client_type=None, **kwargs):
    """
    Backward-compatible wrapper — the original 'openai'/'google' distinction
    is no longer needed. All calls are routed to get_llm_client().
    """
    return get_llm_client()


def parse_structured_output(client, model, messages, response_model):
    """
    Drop-in replacement for client.beta.chat.completions.parse().

    OpenAI's .parse() structured-output endpoint is not available on Groq or
    Mistral.  This helper achieves the same result by:
      1. Appending the Pydantic JSON schema to the prompt.
      2. Requesting JSON mode from the provider.
      3. Validating and returning the parsed Pydantic model instance.

    Usage (replaces the two-liner pattern):
        completion = client.beta.chat.completions.parse(
            model=..., messages=..., response_format=MyModel
        )
        obj = completion.choices[0].message.parsed

    New pattern:
        obj = parse_structured_output(client, model, messages, MyModel)
    """
    schema = response_model.model_json_schema()
    schema_str = json.dumps(schema, indent=2)

    instruction = (
        "\n\nYou MUST reply with ONLY a valid JSON object — no markdown, "
        "no explanations, no code fences. The JSON must conform to this schema:\n"
        + schema_str
    )

    # Build a serialisable copy of the messages list
    msgs = []
    for m in messages:
        if isinstance(m, dict):
            msgs.append(dict(m))
        else:
            # openai ChatCompletionMessage object
            msgs.append({"role": m.role, "content": m.content or ""})

    # Inject the JSON instruction into the last user message
    injected = False
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i].get("role") == "user":
            msgs[i] = {"role": "user", "content": str(msgs[i]["content"]) + instruction}
            injected = True
            break
    if not injected:
        msgs.append({"role": "user", "content": instruction})

    # Gemma 4 via Ollama is a thinking model — JSON mode corrupts its output by
    # mixing internal reasoning tokens into the JSON structure. Without JSON mode,
    # Gemma outputs <think>...</think> then a clean JSON block that the regex below extracts.
    use_json_mode = get_llm_provider() != "ollama"

    kwargs = {"model": model, "messages": msgs}
    if use_json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    else:
        # Gemma 4 (and other thinking models) via Ollama route output to a 'reasoning'
        # field and leave 'content' empty unless thinking is disabled.
        kwargs["extra_body"] = {"think": False}

    completion = client.chat.completions.create(**kwargs)

    token_tracker.add(getattr(completion, "usage", None), model=model)
    content = completion.choices[0].message.content or ""

    # Primary parse attempt
    try:
        data = json.loads(content)
        try:
            return response_model.model_validate(data)
        except Exception:
            pass
        # Gemma 4 sometimes wraps the response in the schema's "properties" key
        # e.g. {"properties": {"value": 100, "reasoning": "..."}} instead of flat
        if isinstance(data, dict) and "properties" in data and isinstance(data["properties"], dict):
            try:
                return response_model.model_validate(data["properties"])
            except Exception:
                pass
    except Exception:
        pass

    # Fallback: extract the first {...} block (handles thinking-model preamble and markdown fences)
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            try:
                return response_model.model_validate(data)
            except Exception:
                pass
            if isinstance(data, dict) and "properties" in data and isinstance(data["properties"], dict):
                try:
                    return response_model.model_validate(data["properties"])
                except Exception:
                    pass
        except Exception:
            pass

    raise ValueError(
        f"parse_structured_output: could not parse model response into "
        f"{response_model.__name__}.\nRaw content:\n{content}"
    )


# ---------------------------------------------------------------------------
# Logging helpers (unchanged from original)
# ---------------------------------------------------------------------------

log_thread_local = threading.local()


class UUIDFormatter(logging.Formatter):
    def format(self, record):
        # Retrieve UUID from thread-local storage, default to 'N/A' if not set
        record.uuid = getattr(log_thread_local, "uuid", "N/A")
        return super().format(record)


def setup_logging():
    logger = logging.getLogger("AgentLogger")
    logger.setLevel(logging.INFO)

    # Prevent adding multiple handlers if setup_logging is called multiple times
    if not logger.handlers:

        # Get the current timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Define the log file path
        log_file_path = f"logs/{timestamp}-run.log"
        os.makedirs("logs", exist_ok=True)
        # Create a FileHandler to write logs to run.log
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setLevel(logging.INFO)

        # Use the custom UUIDFormatter
        formatter = UUIDFormatter(
            "%(asctime)s - %(uuid)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)

        # Add the handler to the logger
        logger.addHandler(file_handler)
