
import logging
import json
import time
import functools
import traceback
import os
from typing import Any, Callable, Dict, Optional
from datetime import datetime, timezone
import uuid

# --- CONFIGURATION ---
LOG_LEVEL = logging.INFO
logging.basicConfig(level=LOG_LEVEL, format="%(message)s")
logger = logging.getLogger("CivicAudit")

class JsonFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings for structured logging.
    """
    def format(self, record):
        log_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        
        # Merge extra fields
        if hasattr(record, "structured_data"):
            log_record.update(record.structured_data)
            
        return json.dumps(log_record)

# Configure the root logger to use JSON formatting
handlers = []

# Console Handler
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(JsonFormatter())
handlers.append(stream_handler)

# File Handler
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
os.makedirs(log_dir, exist_ok=True)
file_handler = logging.FileHandler(os.path.join(log_dir, "agent_trace.jsonl"))
file_handler.setFormatter(JsonFormatter())
handlers.append(file_handler)

# Update the existing logger
if logger.hasHandlers():
    logger.handlers = []
for h in handlers:
    logger.addHandler(h)
logger.setLevel(LOG_LEVEL)

from langchain_community.callbacks import get_openai_callback

# --- OBSERVABILITY DECORATOR ---

def observe_node(event_type: str = "NODE_EXECUTION"):
    """
    Decorator to wrap LangGraph nodes with observability logic.
    Captures input, output, latency, and token usage.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(state: Dict[str, Any], *args, **kwargs):
            start_time = time.perf_counter()
            trace_id = state.get("trace_id", str(uuid.uuid4()))
            span_id = str(uuid.uuid4())
            
            # Capture Input (Sanitized)
            input_summary = str(state)
            if len(input_summary) > 2000:
                input_summary = input_summary[:2000] + "... [TRUNCATED]"

            result = None
            status = "SUCCESS"
            error = None
            token_usage = {}

            try:
                # Execute Node with Token Tracking
                with get_openai_callback() as cb:
                    result = func(state, *args, **kwargs)
                    token_usage = {
                        "total_tokens": cb.total_tokens,
                        "prompt_tokens": cb.prompt_tokens,
                        "completion_tokens": cb.completion_tokens,
                        "total_cost": cb.total_cost
                    }
                
                # Capture Output
                output_summary = str(result)
                if len(output_summary) > 2000:
                    output_summary = output_summary[:2000] + "... [TRUNCATED]"
                
            except Exception as e:
                status = "ERROR"
                error = str(e)
                output_summary = traceback.format_exc()
                raise e
            finally:
                end_time = time.perf_counter()
                latency_ms = (end_time - start_time) * 1000
                
                # Log Structured Event
                log_data = {
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "event_type": event_type,
                    "component": func.__name__,
                    "status": status,
                    "latency_ms": round(latency_ms, 2),
                    "tokens": token_usage,
                    "input": input_summary,
                    "output": output_summary
                }
                
                if error:
                    log_data["error"] = error
                    
                logger.info(f"Executed {func.__name__}", extra={"structured_data": log_data})
                
            return result
        return wrapper
    return decorator
