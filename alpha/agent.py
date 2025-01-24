import logging
import uuid
import functools
import threading
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

from alpha.util import log_thread_local

thread_local = threading.local()

@dataclass
class MessageLogEntry:
    message_type: str
    params: any
    result: any

@dataclass
class MessageLog:
    data: list[MessageLogEntry]


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'to_json') and callable(obj.to_json):
            return obj.to_json()
        return super().default(obj)

def MessageDecorator(cache: bool = False):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, message_type: str, params: any, *args, **kwargs):
            # Generate a UUID
            message_uuid = str(uuid.uuid4())
            
            # Set the UUID in thread-local storage
            current_uuid = getattr(log_thread_local, 'uuid', None)
            log_thread_local.uuid = message_uuid
            
            # Get the AgentLogger
            logger = logging.getLogger("AgentLogger")
            logger.info(f"Starting Message - {message_uuid} Type: {message_type}, Params: {params}")
            
            # Handle caching if enabled
            cache_key = None
            if cache:
                try:
                    params_json = json.dumps(params, cls=CustomJSONEncoder, sort_keys=True)
                except TypeError as e:
                    logger.error(f"Failed to serialize params for caching: {e}")
                    params_json = str(params)  # Fallback to string representation
                
                cache_key = f"{message_type}:{params_json}"
                
                # Initialize cache dictionary on the instance if not present
                if not hasattr(self, '_message_cache'):
                    self._message_cache = {}
                
                if cache_key in self._message_cache:
                    logger.info(f"Cache hit for key: {cache_key}")
                    return self._message_cache[cache_key]
                else:
                    logger.info(f"Cache miss for key: {cache_key}")
            
            try:
                if not hasattr(self, "message_log"):
                    self.message_log = MessageLog(data=[])
                    
                # Call the actual Message method
                result = func(self, message_type, params, *args, logger=logger, **kwargs)
                
                self.message_log.data.append(
                    MessageLogEntry(
                        message_type=message_type,
                        params=params,
                        result=result
                    )
                )
                
                # Log the completion of the message
                logger.info(f"Completed Message with result: {result}")
                
                # Store in cache if enabled
                if cache and cache_key is not None:
                    self._message_cache[cache_key] = result
                
                return result
            finally:
                # Restore the previous UUID in thread-local storage
                if hasattr(log_thread_local, "uuid"):
                    log_thread_local.uuid = current_uuid
        return wrapper
    return decorator

class Agent(ABC):
    
    @property
    def MessageLog(self) -> MessageLog:
        return self.message_log
    
    @abstractmethod
    def RealPerson(self):
        raise NotImplementedError
    
    def NumberOfHumanInteractions(self):
        if not hasattr(self.RealPerson(), "message_log"):
            return 0
        else:
            return len(self.RealPerson().message_log.data)
    
    @abstractmethod
    def Support(self):
        raise NotImplementedError
    
    @abstractmethod
    def Message(self, message_type: str, params: any):
        raise NotImplementedError