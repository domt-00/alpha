import hashlib
import json
import os
import random
import string

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import wraps

import pandas as pd

from alpha.scenario import Bundle, Scenario, Prices
from alpha.agent import Agent


def get_string_hash(input_string):
    return hashlib.sha256(input_string.encode()).hexdigest()


CACHE_PATH = os.path.expanduser("~/.cache/SANDBOX_PERSON_QUERY.csv")
TRANCHE_INFO_CACHE_PATH = os.path.expanduser("~/.cache/SANDBOX_TRANCHE.json")


# Load cache into memory
def load_cache():
    if os.path.exists(CACHE_PATH):
        return pd.read_csv(CACHE_PATH)
    else:
        return pd.DataFrame(
            columns=[
                "scenario_code",
                "seed_code",
                "query_type",
                "query_data",
                "query_result",
                "flag",
                "params",
            ]
        )


# Initialize in-memory cache
df_cache = load_cache()


# Helper function to check if a query exists in cache
def check_cache(scenario_code, seed_code, query_type, query_data, flag, params):
    result = df_cache[
        (df_cache["scenario_code"] == scenario_code)
        & (df_cache["seed_code"] == seed_code)
        & (df_cache["query_type"] == query_type)
        & (df_cache["query_data"] == query_data)
        & (df_cache["flag"] == flag)
        & (df_cache["params"] == params)
    ]
    if not result.empty:
        return result["query_result"].values[0]
    return None


# Function to append new entry to cache in memory and write to file
def update_cache(new_entry):
    global df_cache
    df_cache = pd.concat([df_cache, pd.DataFrame([new_entry])], ignore_index=True)
    df_cache.to_csv(CACHE_PATH, index=False)


TRANCHE_INFO_CACHE_PATH = os.path.expanduser("~/.cache/SANDBOX_TRANCHE.json")


def random_code():
    return "".join([random.choice(string.ascii_uppercase) for _ in range(6)])


@dataclass
class Seed:
    code: str
    scenario: str
    description: str

    def __str__(self):
        return (
            "Seed " + self.code + " under " + self.scenario + "\n\n" + self.description
        )

    def to_json(self):
        return json.dumps(
            {
                "code": self.code,
                "scenario": self.scenario,
                "description": self.description,
            }
        )
        
    def Description(self):
        return self.description

    @classmethod
    def from_json(cls, s):
        data = json.loads(s)

        return cls(
            code=data["code"],
            scenario=data["scenario"],
            description=data["description"],
        )
        

class SeedGenerationPipeline(ABC):
    
    @abstractmethod
    def __call__(self, scenario: Scenario) -> Seed:
        raise NotImplementedError
    
    def generate(self, scenario: Scenario, k: int):
        # Use ThreadPoolExecutor to run __call__ in parallel
        seeds = []
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(self.__call__, scenario) for _ in range(k)]
            
            for future in as_completed(futures):
                seeds.append(future.result())
        
        return seeds


def value_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Extract the keyword arguments cached and flag
        use_cache = kwargs.get("use_cache", False)
        flag = kwargs.get("flag", 0)

        # Extract the necessary elements to form the cache key
        scenario = kwargs.get("scenario")
        seed = kwargs.get("seed")
        bundle = kwargs.get("bundle")

        if hasattr(args[0], "params"):
            params = getattr(args[0], "params")

        if scenario is None or seed is None or bundle is None:
            raise ValueError(
                "Scenario, seed, and bundle are required keyword arguments"
            )
        # Check if the result is already in cache
        if use_cache:
            use_cache = check_cache(
                scenario.code, seed.code, "value_query", str(bundle), flag, params
            )
            if use_cache is not None:
                return use_cache

        # If not cached, call the function and cache the result
        result = func(*args, **kwargs)

        if use_cache:
            # Update the cache with the new result
            update_cache(
                {
                    "scenario_code": scenario.code,
                    "seed_code": seed.code,
                    "query_type": "value_query",
                    "query_data": str(bundle),
                    "query_result": result,
                    "flag": flag,
                    "params": params,
                }
            )

        return result

    return wrapper


class ValuePipeline(ABC):
    
    @abstractmethod
    def __call__(
        self,
        scenario: Scenario = None,
        seed: Seed = None,
        bundle: Bundle = None,
        use_cache: bool = False,
        flag: int = 0,
        logger = None
    ) -> float:
        raise NotImplementedError


class QuestionPipeline(ABC):
    
    @abstractmethod
    def __call__(
        self, scenario: Scenario = None, seed: Seed = None, question: str = None, logger = None
    ) -> float:
        raise NotImplementedError

class EquivalencePipeline(ABC):
    
    @abstractmethod
    def __call__(
        self, scenario: Scenario = None, seed: Seed = None, prices: Prices = None, bundle: Bundle = None, logger = None
    ):
        raise NotImplementedError

class Person(Agent):
    
    def Support(self):
        return ["question", "value", "demand"]

    def RealPerson(self):
        return self

