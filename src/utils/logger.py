"""
Observability Utilities.

Provides a LangGraph node decorator that ships telemetry to Langfuse.
Console logging is kept for local visibility at DEBUG level.
"""

import functools
import logging
import time
from typing import Any, Callable, Optional, TypeVar

from langchain_community.callbacks import get_openai_callback

# --- TYPE VARIABLES ---
F = TypeVar("F", bound=Callable[..., Any])

# --- LOGGING SETUP ---
LOG_LEVEL = logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("CivicAudit")


# --- HELPERS ---


def _build_input_summary(state: dict[str, Any]) -> dict[str, Any]:
    """Extract relevant input fields from state for Langfuse (no blob fields)."""
    relevant = ("user_question", "sql_query", "error", "evaluation", "iterations")
    result: dict[str, Any] = {}
    for k in relevant:
        v = state.get(k)
        if v is None:
            continue
        result[k] = v[:500] if isinstance(v, str) and len(v) > 500 else v
    return result


def _build_output_summary(result: Any) -> Any:
    """Truncate output for Langfuse."""
    if result is None:
        return None
    if isinstance(result, dict):
        return {
            k: (v[:500] if isinstance(v, str) and len(v) > 500 else v)
            for k, v in result.items()
        }
    s = str(result)
    return s[:1000] if len(s) > 1000 else s


# --- OBSERVABILITY DECORATOR ---


def observe_node(
    event_type: str = "NODE_EXECUTION", model_key: Optional[str] = None
) -> Callable[[F], F]:
    """
    Decorator that wraps LangGraph nodes with Langfuse observability.

    Creates a Langfuse span (TOOL_CALL / GUARDRAIL) or generation (THOUGHT)
    for each node execution, linked to the parent trace via state["trace_id"].
    If Langfuse is not configured, the node executes normally with no side effects.

    Args:
        event_type: "THOUGHT" (LLM call), "TOOL_CALL", or "GUARDRAIL".
        model_key: Config key for the LLM model (e.g. "fiscal_model").
                   Required for THOUGHT nodes so Langfuse can log the model name.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(state: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
            from src.utils.langfuse_client import get_langfuse_client

            lf = get_langfuse_client()
            trace_id: Optional[str] = state.get("trace_id")
            root_span_id: Optional[str] = state.get("root_span_id")

            start_time = time.perf_counter()
            status = "SUCCESS"
            error_msg: Optional[str] = None
            span = None

            # Token counters — always defined so finally block can reference them
            total_tokens = prompt_tokens = completion_tokens = 0
            total_cost = 0.0

            # --- Create Langfuse span or generation ---
            if lf and trace_id:
                try:
                    from langfuse.types import TraceContext

                    ctx = TraceContext(trace_id=trace_id)
                    if root_span_id:
                        ctx = TraceContext(
                            trace_id=trace_id, parent_span_id=root_span_id
                        )

                    input_data = _build_input_summary(state)

                    iteration = state.get("iterations", 0)

                    if event_type == "THOUGHT":
                        from src.config import get_settings

                        settings = get_settings()
                        model_name = (
                            settings.get("agent", {}).get(model_key, "unknown")
                            if model_key
                            else "unknown"
                        )
                        span = lf.start_generation(
                            name=func.__name__,
                            model=model_name,
                            input=input_data,
                            trace_context=ctx,
                            metadata={
                                "event_type": event_type,
                                "iteration": iteration,
                                "is_retry": iteration > 0,
                            },
                        )
                    else:
                        span = lf.start_span(
                            name=func.__name__,
                            input=input_data,
                            trace_context=ctx,
                            metadata={"event_type": event_type},
                        )
                except Exception as lf_err:
                    logger.debug("Langfuse span creation error: %s", lf_err)

            # --- Execute node ---
            result = None
            try:
                with get_openai_callback() as cb:
                    result = func(state, *args, **kwargs)
                total_tokens = cb.total_tokens
                prompt_tokens = cb.prompt_tokens
                completion_tokens = cb.completion_tokens
                total_cost = cb.total_cost
            except Exception as e:
                status = "ERROR"
                error_msg = str(e)
                raise
            finally:
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

                # --- Finalise Langfuse span ---
                if span:
                    try:
                        span.update(
                            output=_build_output_summary(result),
                            metadata={
                                "event_type": event_type,
                                "latency_ms": latency_ms,
                                "status": status,
                                "cost_usd": total_cost,
                            },
                            level="ERROR" if status == "ERROR" else "DEFAULT",
                            status_message=error_msg,
                        )
                        if event_type == "THOUGHT" and total_tokens > 0:
                            span.update(
                                usage_details={
                                    "input": prompt_tokens,
                                    "output": completion_tokens,
                                    "total": total_tokens,
                                },
                                cost_details={"total": total_cost},
                            )
                        span.end()
                    except Exception as lf_err:
                        logger.debug("Langfuse span end error: %s", lf_err)

                logger.debug(
                    "node=%s status=%s latency=%.0fms tokens=%d cost=$%.4f",
                    func.__name__,
                    status,
                    latency_ms,
                    total_tokens,
                    total_cost,
                )

            return result

        return wrapper  # type: ignore[return-value]

    return decorator
