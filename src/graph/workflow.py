"""
Audit Workflow Graph.

Main orchestrator for the CivicAudit workflow integrating all agents.
"""

import logging
import uuid
from typing import Literal, Optional, cast

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from src.agents.analyst import (
    check_execution,
    critique,
    execute,
    generate,
    should_continue,
    simple_execute,
)
from src.agents.editor import editor
from src.agents.fiscal import (
    check_query_node,
    generate_query_node,
    get_schema_node,
    list_tables_node,
)
from src.agents.guardrail import guardrail_input, guardrail_output
from src.agents.integrity import check_result_integrity
from src.agents.planner import planner
from src.schemas.state import AgentState
from src.utils.langfuse_client import get_langfuse_client

logger = logging.getLogger(__name__)


class AuditResponse(BaseModel):
    """Typed, validated output of a completed audit workflow run."""

    answer: str
    trace_id: str = ""
    data_gap_detected: bool = False
    gap_reason: Optional[Literal["empty_result", "data_unavailable"]] = None
    iterations: int = 0
    route_path: str = ""


def check_guardrail(state: AgentState) -> str:
    """
    Route based on guardrail verdict and query complexity.

    Complexity is determined semantically by guardrail_input via embedding similarity
    against pre-computed complexity anchors (stored in state.is_complex).
    Falls back to simple routing when the embedding index is unavailable.

    Returns:
        "planner" if safe and complex, "list_tables" if safe and simple, END if blocked.
    """
    verdict = state.get("guardrail_verdict")
    if verdict == "UNSAFE":
        logger.debug("DECISION: BLOCKED BY GUARDRAIL")
        return cast(str, END)

    is_complex = state.get("is_complex", False)
    if is_complex:
        logger.debug("DECISION: COMPLEX QUERY (semantic) -> PLANNER")
        return "planner"

    logger.debug("DECISION: SIMPLE QUERY -> SKIP PLANNER -> list_tables")
    return "list_tables"


def _is_simple_sql(state: AgentState) -> bool:
    """
    Detect whether the generated SQL can be executed directly without Python codegen.

    Simple = single SELECT with no GROUP BY, no subqueries, no CTEs.
    JOINs are allowed — dimension lookups don't add analytical complexity.

    Complex queries (breakdowns, rankings, multi-step, window functions) still
    use the full generate → critic → execute pipeline.
    """
    sql = (state.get("sql_query") or "").upper()
    is_structurally_complex = (
        sql.count("SELECT") > 1 or "WITH " in sql or "GROUP BY" in sql
    )
    return not is_structurally_complex


def check_sql_generated(state: AgentState) -> str:
    """
    Route based on whether SQL was successfully generated.

    Returns:
        "check_sql" if SQL was generated, END if generation failed.
    """
    if not state.get("sql_query"):
        logger.debug("DECISION: NO SQL GENERATED -> END")
        return cast(str, END)
    return "check_sql"


def check_sql_validated(state: AgentState) -> str:
    """
    Route based on whether SQL passed validation and query complexity.

    Returns:
        "simple_execute" for simple aggregations, "generate" for complex queries,
        END if validation failed.
    """
    if not state.get("sql_query"):
        logger.debug("DECISION: SQL VALIDATION FAILED -> END")
        return cast(str, END)
    if _is_simple_sql(state):
        logger.debug("DECISION: SIMPLE SQL -> SKIP ANALYST -> simple_execute")
        return "simple_execute"
    return "generate"


def _infer_route_path(final_state: dict) -> str:
    """Infer which pipeline route was taken from the final state."""
    if final_state.get("guardrail_verdict") == "UNSAFE":
        return "blocked"
    iterations = final_state.get("iterations", 0)
    if iterations == 0 and final_state.get("sql_query"):
        return "simple_sql"
    if final_state.get("plan"):
        return "complex_with_planner"
    return "complex"


def _compute_trajectory_efficiency(route_path: str, iterations: int) -> float:
    """
    Ratio of minimum required steps to actual steps taken.

    1.0 = perfect (no retries, no redundant steps).
    < 1.0 = retries caused extra generate+critic cycles.

    Minimum node counts per path:
      blocked         → 1  (guardrail_input only)
      simple_sql      → 8  (guardrail→list→schema→sql→check→
                            simple_execute→editor→guardrail_out)
      complex         → 11 (+ generate→critic→execute)
      complex_planner → 12 (+ planner)
    """
    if route_path in ("blocked", "simple_sql"):
        return 1.0
    base = 12 if route_path == "complex_with_planner" else 11
    # Each iteration beyond the first adds generate + critic again
    extra = max(0, iterations - 1) * 2
    return round(base / (base + extra), 3) if (base + extra) > 0 else 1.0


class AuditGraph:
    """
    Main orchestrator for the CivicAudit workflow.

    Integrates:
    - Input Guardrail
    - Planner Agent
    - Fiscal Agent (SQL Specialist)
    - Analyst Agent (Python Specialist)
    - Critic Agent
    - Output Guardrail
    """

    def __init__(self) -> None:
        """Initialize the audit workflow graph."""
        self.memory = MemorySaver()
        self.graph = self._build_graph()
        self.last_thread_id: Optional[str] = None

    def _build_graph(self) -> StateGraph:
        """
        Build and compile the workflow graph.

        Returns:
            Compiled StateGraph ready for execution.
        """
        workflow = StateGraph(AgentState)

        # --- NODES ---
        workflow.add_node("guardrail_input", guardrail_input)
        workflow.add_node("planner", planner)

        # Fiscal Agent Nodes (SQL Specialist)
        workflow.add_node("list_tables", list_tables_node)
        workflow.add_node("get_schema", get_schema_node)
        workflow.add_node("generate_sql", generate_query_node)
        workflow.add_node("check_sql", check_query_node)

        # Analyst Agent Nodes (Python Specialist)
        workflow.add_node("simple_execute", simple_execute)
        workflow.add_node("generate", generate)
        workflow.add_node("critic", critique)
        workflow.add_node("execute", execute)
        workflow.add_node("check_result_integrity", check_result_integrity)
        workflow.add_node("editor", editor)
        workflow.add_node("guardrail_output", guardrail_output)

        # --- EDGES ---

        # Entry Point
        workflow.set_entry_point("guardrail_input")

        # Guardrail -> Complexity check -> Planner or directly to Fiscal Agent
        workflow.add_conditional_edges(
            "guardrail_input",
            check_guardrail,
            {"planner": "planner", "list_tables": "list_tables", END: END},
        )

        # Planner -> Fiscal Agent Pipeline
        workflow.add_edge("planner", "list_tables")
        workflow.add_edge("list_tables", "get_schema")
        workflow.add_edge("get_schema", "generate_sql")

        # Short-circuit after generate_sql when sql_query is None
        workflow.add_conditional_edges(
            "generate_sql",
            check_sql_generated,
            {"check_sql": "check_sql", END: END},
        )

        # Short-circuit after check_sql when SQL failed validation or gap detected
        workflow.add_conditional_edges(
            "check_sql",
            check_sql_validated,
            {
                "simple_execute": "simple_execute",
                "generate": "generate",
                "editor": "editor",
                END: END,
            },
        )

        # Simple path: direct SQL execution → integrity check → editor
        workflow.add_edge("simple_execute", "check_result_integrity")

        # Analyst Agent Loop (Generate Code -> Critic -> Execute)
        workflow.add_edge("generate", "critic")

        workflow.add_conditional_edges(
            "critic",
            should_continue,
            {
                "generate": "generate",
                "execute": "execute",
                "abort": "guardrail_output",
            },
        )

        # Execute -> integrity check -> Editor -> Output Guardrail
        workflow.add_conditional_edges(
            "execute",
            check_execution,
            {"generate": "generate", END: "check_result_integrity"},
        )

        workflow.add_edge("check_result_integrity", "editor")
        workflow.add_edge("editor", "guardrail_output")

        # Output -> End
        workflow.add_edge("guardrail_output", END)

        return workflow.compile(checkpointer=self.memory)  # type: ignore

    def _create_trace(
        self, user_question: str, thread_id: str, **metadata: object
    ) -> tuple:
        """
        Create a Langfuse root span for a workflow run.

        Returns:
            (root_span | None, trace_id: str, root_span_id: str)
            IDs are always valid hex strings even when Langfuse is disabled.
        """
        import os

        lf = get_langfuse_client()
        root_span = None
        trace_id: str = os.urandom(16).hex()
        root_span_id: str = os.urandom(8).hex()

        if lf:
            try:
                trace_id = lf.create_trace_id()
                root_span = lf.start_span(
                    name="audit-query",
                    input={"question": user_question},
                    metadata={"thread_id": thread_id, **metadata},
                )
                root_span_id = root_span.id
                trace_id = root_span.trace_id
            except Exception as e:
                logger.debug("Langfuse root span creation failed: %s", e)

        return root_span, trace_id, root_span_id

    def _finalize_trace(
        self,
        root_span: object,
        final_state: dict,
        thread_id: str,
        tags: Optional[list] = None,
        latency_ms: float = 0.0,
    ) -> None:
        """
        Update the Langfuse root span with final results and emit all scores.
        Safe to call even when Langfuse is disabled (root_span is None).

        Scores emitted
        ─────────────────────────────────────────────────────────
        Task Performance
          workflow_completed      BOOLEAN  — output produced without fatal error
          execution_success       BOOLEAN  — sandbox / SQL execution had no error
          guardrail_safe          BOOLEAN  — input passed the safety check

        Trajectory & Path
          route_path              CATEGORICAL — blocked/simple_sql/
                                              complex/complex_with_planner
          planner_invoked         BOOLEAN  — planner node was called
          simple_sql_path         BOOLEAN  — bypassed Python codegen + Docker
          critic_approved_1st_try BOOLEAN  — critic approved without any retry
          trajectory_efficiency   NUMERIC  — min_steps / actual_steps (1.0 = perfect)
          retries_used            NUMERIC  — total analyst/critic retry cycles

        Tool Call & Execution
          sql_generated           BOOLEAN  — fiscal agent produced a valid SQL query

        Efficiency
          total_latency_ms        NUMERIC  — end-to-end wall-clock time
        ─────────────────────────────────────────────────────────
        Token cost/utilisation is automatically aggregated by Langfuse from
        the individual generation spans (no manual score needed).
        """
        # ── Always log metrics to terminal ───────────────────────────────────
        iterations = final_state.get("iterations", 0)
        sql_query = final_state.get("sql_query")
        has_error = bool(final_state.get("error"))
        has_output = bool(final_state.get("output"))
        route_path = _infer_route_path(final_state)
        guardrail_verdict = final_state.get("guardrail_verdict", "")
        simple_path = iterations == 0 and bool(sql_query) and not has_error
        traj_eff = _compute_trajectory_efficiency(route_path, iterations)
        data_gap = final_state.get("data_gap_detected", False)
        logger.info(
            "\n── Run Metrics ──────────────────────────────────────\n"
            "  route_path             : %s\n"
            "  guardrail_safe         : %s\n"
            "  workflow_completed     : %s\n"
            "  execution_success      : %s\n"
            "  sql_generated          : %s\n"
            "  planner_invoked        : %s\n"
            "  simple_sql_path        : %s\n"
            "  data_gap_detected      : %s\n"
            "  gap_reason             : %s\n"
            "  critic_approved_1st    : %s\n"
            "  retries_used           : %d\n"
            "  trajectory_efficiency  : %.3f\n"
            "  total_latency_ms       : %.0f ms\n"
            "─────────────────────────────────────────────────────",
            route_path,
            guardrail_verdict == "SAFE",
            has_output and not has_error,
            not has_error,
            bool(sql_query),
            final_state.get("plan") is not None,
            simple_path,
            data_gap,
            final_state.get("gap_reason") or "—",
            iterations <= 1,
            iterations,
            traj_eff,
            latency_ms,
        )

        if not root_span:
            return
        try:
            root_span.update_trace(  # type: ignore[attr-defined]
                session_id=thread_id,
                output=str(final_state.get("output", "")),
                metadata={
                    "route_path": route_path,
                    "tables_selected": final_state.get("table_list", []),
                    "sql_query": sql_query,
                    "total_iterations": iterations,
                    "planner_invoked": final_state.get("plan") is not None,
                    "total_latency_ms": round(latency_ms, 2),
                },
                tags=tags or ["audit", "agent"],
            )
            root_span.end()  # type: ignore[attr-defined]

            def _score(
                name: str, value: float | str, data_type: str, **kw: object
            ) -> None:
                root_span.score_trace(  # type: ignore[attr-defined]
                    name=name, value=value, data_type=data_type, **kw
                )

            # ── Task Performance ──────────────────────────────────────────
            if guardrail_verdict:
                _score(
                    "guardrail_safe",
                    1.0 if guardrail_verdict == "SAFE" else 0.0,
                    "BOOLEAN",
                    comment=guardrail_verdict,
                )
            _score(
                "workflow_completed",
                1.0 if (has_output and not has_error) else 0.0,
                "BOOLEAN",
            )
            _score("execution_success", 0.0 if has_error else 1.0, "BOOLEAN")

            # ── Trajectory & Path ─────────────────────────────────────────
            _score("route_path", route_path, "CATEGORICAL")
            _score(
                "planner_invoked", 1.0 if final_state.get("plan") else 0.0, "BOOLEAN"
            )
            _score("simple_sql_path", 1.0 if simple_path else 0.0, "BOOLEAN")
            _score(
                "critic_approved_1st_try",
                1.0 if iterations <= 1 else 0.0,
                "BOOLEAN",
            )
            _score("trajectory_efficiency", traj_eff, "NUMERIC")
            _score("retries_used", float(iterations), "NUMERIC")

            # ── Tool Call & Execution ─────────────────────────────────────
            _score("sql_generated", 1.0 if sql_query else 0.0, "BOOLEAN")

            # ── Data Gap Detection ────────────────────────────────────────
            data_gap = final_state.get("data_gap_detected", False)
            _score("data_gap_detected", 1.0 if data_gap else 0.0, "BOOLEAN")
            gap_reason = final_state.get("gap_reason") or ""
            if gap_reason:
                _score("gap_reason", gap_reason, "CATEGORICAL")
            gap_recovery = bool(data_gap and final_state.get("gap_alternative"))
            _score("gap_recovery_presented", 1.0 if gap_recovery else 0.0, "BOOLEAN")

            # ── Efficiency ────────────────────────────────────────────────
            if latency_ms > 0:
                _score("total_latency_ms", round(latency_ms, 2), "NUMERIC")

        except Exception as e:
            logger.debug("Langfuse trace finalization failed: %s", e)

    def run(self, user_question: str, thread_id: Optional[str] = None) -> str:
        """
        Execute the audit workflow for a user question.

        Supports multi-turn conversations: if thread_id is provided (or reused
        from self.last_thread_id), the conversation history is preserved via
        MemorySaver. Use self.last_thread_id after each call to continue the
        same conversation thread.

        Args:
            user_question: The user's audit question.
            thread_id: Thread ID for conversation continuity. If None, starts
                       a new conversation with a fresh thread_id.

        Returns:
            The final formatted output from the workflow.
        """
        is_new_conversation = thread_id is None
        thread_id = thread_id or str(uuid.uuid4())
        self.last_thread_id = thread_id

        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 30,
        }

        root_span, trace_id, root_span_id = self._create_trace(
            user_question, thread_id, is_new_conversation=is_new_conversation
        )

        inputs: dict = {
            "messages": [HumanMessage(content=user_question)],
            "iterations": 0,
            "trace_id": trace_id,
            "root_span_id": root_span_id,
            # Gap fields are per-query — always reset to avoid stale state between turns
            "data_gap_detected": False,
            "gap_reason": None,
            "gap_detail": None,
            "gap_alternative": None,
            "gap_context": None,
        }

        # For new conversations, reset transient state.
        # For follow-ups (thread_id provided), preserve prior sql_query and context.
        if is_new_conversation:
            inputs.update({"error": None, "evaluation": None, "sql_query": None})

        import time

        final_state: dict = {}
        t_start = time.perf_counter()
        try:
            final_state = self.graph.invoke(inputs, config=config)  # type: ignore
        except Exception as e:
            logger.error("Workflow error for thread %s: %s", thread_id, e)
            if root_span:
                try:
                    root_span.update(  # type: ignore[attr-defined]
                        output=f"Workflow error: {e}",
                        level="ERROR",
                        status_message=str(e),
                    )
                    root_span.end()  # type: ignore[attr-defined]
                except Exception:
                    pass
            return f"Erro interno no processamento da consulta: {e}"

        latency_ms = (time.perf_counter() - t_start) * 1000
        self._finalize_trace(
            root_span, dict(final_state), thread_id, latency_ms=latency_ms
        )
        return str(final_state.get("output", "Nenhum resultado gerado."))

    def run_structured(
        self, user_question: str, thread_id: Optional[str] = None
    ) -> AuditResponse:
        """
        Execute the audit workflow and return a typed, validated response.

        Same execution as run() but returns AuditResponse instead of str,
        giving callers structured access to gap detection, trace ID, and
        routing metadata without parsing the output string.

        Args:
            user_question: The user's audit question.
            thread_id: Thread ID for conversation continuity.

        Returns:
            AuditResponse with answer, trace info, and gap metadata.
        """
        is_new_conversation = thread_id is None
        thread_id = thread_id or str(uuid.uuid4())
        self.last_thread_id = thread_id

        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 30,
        }

        root_span, trace_id, root_span_id = self._create_trace(
            user_question, thread_id, is_new_conversation=is_new_conversation
        )

        inputs: dict = {
            "messages": [HumanMessage(content=user_question)],
            "iterations": 0,
            "trace_id": trace_id,
            "root_span_id": root_span_id,
            # Gap fields are per-query — always reset to avoid stale state between turns
            "data_gap_detected": False,
            "gap_reason": None,
            "gap_detail": None,
            "gap_alternative": None,
            "gap_context": None,
        }
        if is_new_conversation:
            inputs.update({"error": None, "evaluation": None, "sql_query": None})

        import time

        final_state: dict = {}
        t_start = time.perf_counter()
        try:
            final_state = self.graph.invoke(inputs, config=config)  # type: ignore
        except Exception as e:
            logger.error("Workflow error for thread %s: %s", thread_id, e)
            return AuditResponse(
                answer=f"Erro interno no processamento da consulta: {e}",
                trace_id=trace_id,
            )

        latency_ms = (time.perf_counter() - t_start) * 1000
        self._finalize_trace(
            root_span, dict(final_state), thread_id, latency_ms=latency_ms
        )

        gap_reason_raw = final_state.get("gap_reason")
        gap_reason: Optional[Literal["empty_result", "data_unavailable"]] = (
            gap_reason_raw
            if gap_reason_raw in ("empty_result", "data_unavailable")
            else None
        )

        return AuditResponse(
            answer=str(final_state.get("output", "Nenhum resultado gerado.")),
            trace_id=str(final_state.get("trace_id", trace_id)),
            data_gap_detected=bool(final_state.get("data_gap_detected", False)),
            gap_reason=gap_reason,
            iterations=int(final_state.get("iterations", 0)),
            route_path=_infer_route_path(final_state),
        )
