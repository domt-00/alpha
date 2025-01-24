import itertools
import threading
import logging
import random
import os
import time
import traceback
import inspect
from functools import wraps
from datetime import datetime

import google.auth
import google.auth.transport.requests
import openai

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

def retry(max_attempts=20, delay=1, expansion=2, use_default=False, default=None, exceptions=(Exception,)):
    """
    A decorator that retries a function call if an exception is raised.
    
    Parameters:
    - max_attempts: The maximum number of retry attempts.
    - delay: The initial delay (in seconds) between retries.
    - expansion: The factor by which the delay increases after each attempt.
    - use_default: If True, returns the default value upon failure instead of raising the exception.
    - default: The default value to return if use_default is True.
    - exceptions: A tuple of exception classes to catch and retry upon.
    
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
                    
                    if attempt < max_attempts:
                        print(f"Retrying in {current_delay:.2f} seconds...\n")
                        time.sleep(current_delay)
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

def get_openai_client(client_type, project_id=None, location=None):
    """
    Initializes the OpenAI client to use the specified model.
    
    Parameters:
    - model: The model identifier (e.g., "gpt-4", "google/gemini-1.5-flash")
    - project_id: Google Cloud project ID (required for Gemini models)
    - location: Google Cloud location (required for Gemini models)
    - endpoint_id: Vertex AI endpoint ID for self-deployed models (optional)
    
    Returns:
    - An initialized OpenAI client.
    """
    
    if client_type == "google":
        if project_id is None:
            project_id = os.environ["GCP_PROJECT_ID"]
        if location is None:
            location = os.environ["GCP_LOCATION"]
        # Authenticate with Google credentials
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
            quota_project_id=project_id
        )
        auth_req = google.auth.transport.requests.Request()
        creds.refresh(auth_req)
        
        base_url = f'https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project_id}/locations/{location}/endpoints/openapi'
        
        client = openai.OpenAI(
            base_url=base_url,
            api_key=creds.token,
        )
    elif client_type == "openai":
        # For OpenAI models, use the default OpenAI client
        client = openai.OpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )
    else:
        raise ValueError(f"Invalid client type '{client_type}'")
    
    return client


log_thread_local = threading.local()


class UUIDFormatter(logging.Formatter):
    def format(self, record):
        # Retrieve UUID from thread-local storage, default to 'N/A' if not set

        record.uuid = getattr(log_thread_local, 'uuid', 'N/A')
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
            '%(asctime)s - %(uuid)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        # Add the handler to the logger
        logger.addHandler(file_handler)