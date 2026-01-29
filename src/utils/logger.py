"""
Observability and Logging Utilities.

Provides structured JSON logging and LangGraph node observability decorator.
"""

import functools
import json
import logging
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from langchain_community.callbacks import get_openai_callback

# --- TYPE VARIABLES ---
F = TypeVar("F", bound=Callable[..., Any])

# --- CONFIGURATION ---
LOG_LEVEL = logging.INFO
logging.basicConfig(level=LOG_LEVEL, format="%(message)s")
logger = logging.getLogger("CivicAudit")


class JsonFormatter(logging.Formatter):
    """Formatter that outputs JSON strings for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a JSON string."""
        log_record: dict[str, Any] = {
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
_handlers: list[logging.Handler] = []

# Console Handler
_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(JsonFormatter())
_handlers.append(_stream_handler)

# File Handler
_log_dir = Path(__file__).parent.parent.parent / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)
_file_handler = logging.FileHandler(_log_dir / "agent_trace.jsonl")
_file_handler.setFormatter(JsonFormatter())
_handlers.append(_file_handler)

# Update the existing logger
if logger.hasHandlers():
    logger.handlers = []
for h in _handlers:
    logger.addHandler(h)
logger.setLevel(LOG_LEVEL)


# --- OBSERVABILITY DECORATOR ---


def observe_node(event_type: str = "NODE_EXECUTION") -> Callable[[F], F]:
    """
    Decorator to wrap LangGraph nodes with observability logic.

    Captures input, output, latency, and token usage for each node execution.

    Args:
        event_type: Type of event to log (e.g., "THOUGHT", "TOOL_CALL").

    Returns:
        Decorated function with observability.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(state: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
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
            token_usage: dict[str, Any] = {}

            try:
                # Execute Node with Token Tracking
                with get_openai_callback() as cb:
                    result = func(state, *args, **kwargs)
                    token_usage = {
                        "total_tokens": cb.total_tokens,
                        "prompt_tokens": cb.prompt_tokens,
                        "completion_tokens": cb.completion_tokens,
                        "total_cost": cb.total_cost,
                    }

                # Capture Output
                output_summary = str(result)
                if len(output_summary) > 2000:
                    output_summary = output_summary[:2000] + "... [TRUNCATED]"

            except Exception as e:
                status = "ERROR"
                error = str(e)
                output_summary = traceback.format_exc()
                raise
            finally:
                end_time = time.perf_counter()
                latency_ms = (end_time - start_time) * 1000

                # Log Structured Event
                log_data: dict[str, Any] = {
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "event_type": event_type,
                    "component": func.__name__,
                    "status": status,
                    "latency_ms": round(latency_ms, 2),
                    "tokens": token_usage,
                    "input": input_summary,
                    "output": output_summary,
                }

                if error:
                    log_data["error"] = error

                logger.info(
                    "Executed %s", func.__name__, extra={"structured_data": log_data}
                )

            return result

        return wrapper  # type: ignore[return-value]

    return decorator
