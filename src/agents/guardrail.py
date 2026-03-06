"""
Guardrail Agent Node Functions.

Input and output safety validation for the audit workflow.
"""

import logging
import re
from typing import Any, Optional, cast

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate

from src.schemas.state import AgentState
from src.utils.llm import get_llm
from src.utils.logger import observe_node
from src.utils.prompts import load_prompt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fast-path deterministic guardrail — runs before the LLM check
# ---------------------------------------------------------------------------

# Keywords that clearly indicate a public audit / fiscal query
_FISCAL_KEYWORDS: frozenset[str] = frozenset(
    {
        "despesa",
        "despesas",
        "gasto",
        "gastos",
        "pago",
        "pagamento",
        "pagamentos",
        "receita",
        "receitas",
        "arrecadação",
        "arrecadacao",
        "arrecadado",
        "licitação",
        "licitações",
        "licitacao",
        "licitacoes",
        "contrato",
        "contratos",
        "fornecedor",
        "fornecedores",
        "contratado",
        "orçamento",
        "orcamento",
        "empenho",
        "empenhos",
        "liquidado",
        "liquidação",
        "servidor",
        "servidores",
        "agente",
        "agentes",
        "educação",
        "educacao",
        "saúde",
        "saude",
        "administração",
        "administracao",
        "sobral",
        "municipio",
        "município",
        "cidade",
        "prefeitura",
        "tce",
        "auditoria",
        "transparência",
        "transparencia",
        "nota fiscal",
        "notas fiscais",
        "balancete",
        "orçamentário",
        "orcamentario",
        "função",
        "funcao",
        "programa",
        "órgão",
        "orgao",
        "secretaria",
        "licitante",
        "licitantes",
        "pregão",
        "pregao",
        "dispensa",
    }
)

# Simple greeting patterns — always safe
_GREETING_PATTERNS: frozenset[str] = frozenset(
    {
        "bom dia",
        "boa tarde",
        "boa noite",
        "olá",
        "ola",
        "oi",
        "hi",
        "hello",
        "tudo bem",
        "tudo bom",
        "como vai",
    }
)

# Patterns that indicate a suspicious / injection attempt
_SUSPICIOUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(previous|above|all|your)", re.IGNORECASE),
    re.compile(r"\b(system|assistant|human)\s*:", re.IGNORECASE),
    re.compile(r"\b(jailbreak|dan\s+mode|developer\s+mode)\b", re.IGNORECASE),
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"\b(rm\s+-rf|sudo|chmod|curl|wget)\b", re.IGNORECASE),
]


def _fast_path_verdict(text: str) -> Optional[str]:
    """
    Deterministic guardrail check — no LLM required.

    Returns "SAFE" if the query is obviously a fiscal audit query or greeting.
    Returns "UNSAFE" if suspicious patterns are detected.
    Returns None if the query is ambiguous (LLM check needed).

    Args:
        text: The user input to evaluate.

    Returns:
        "SAFE", "UNSAFE", or None (defer to LLM).
    """
    if len(text) > 600:
        return None  # Long inputs deferred to LLM for thorough analysis

    text_lower = text.lower()

    # Block if any suspicious pattern matches
    for pattern in _SUSPICIOUS_PATTERNS:
        if pattern.search(text_lower):
            return "UNSAFE"

    # Fast-approve greetings
    if any(greet in text_lower for greet in _GREETING_PATTERNS):
        return "SAFE"

    # Fast-approve clearly fiscal queries
    words = re.findall(r"[\w\u00c0-\u024f]+", text_lower)
    word_set = set(words)
    if word_set & _FISCAL_KEYWORDS:
        return "SAFE"

    return None  # Ambiguous — let the LLM decide


# ---------------------------------------------------------------------------
# Deterministic PII redaction patterns — no LLM needed
# ---------------------------------------------------------------------------

# Deterministic PII redaction patterns — no LLM needed
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"), "[CPF REDACTED]"),
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[EMAIL REDACTED]",
    ),  # noqa: E501
    (re.compile(r"\(\d{2}\)\s?\d{4,5}-\d{4}"), "[TELEFONE REDACTED]"),
    (re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b"), "[API_KEY REDACTED]"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[CARD REDACTED]"),
]


def _redact_pii(text: str) -> str:
    """Apply all PII redaction patterns to text."""
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _semantic_route(user_input: str) -> dict[str, Any]:
    """
    Run semantic table selection and complexity detection for a SAFE query.

    Reads thresholds from config.yaml (embeddings section).
    Returns a dict with 'selected_tables' and 'is_complex' to merge into state.
    Never raises — falls back to empty/False if the embedding index is unavailable.
    """
    try:
        from src.config import get_settings
        from src.utils.embeddings import analyze_question

        cfg = get_settings().get("embeddings", {})
        selected_tables, is_complex = analyze_question(
            user_input,
            top_k=int(cfg.get("top_k", 4)),
            complexity_threshold=float(cfg.get("complexity_threshold", 0.62)),
            min_score=float(cfg.get("min_table_score", 0.30)),
        )
        return {"selected_tables": selected_tables, "is_complex": is_complex}
    except Exception as e:
        logger.warning("Semantic routing failed (index may not be built): %s", e)
        return {"selected_tables": [], "is_complex": False}


@observe_node(event_type="GUARDRAIL", model_key="guardrail_model")
def guardrail_input(state: AgentState) -> dict[str, Any]:
    """
    Validate user input for safety and relevance.

    Args:
        state: Current agent state containing user messages.

    Returns:
        Updated state with guardrail verdict and optional blocked output.
    """
    messages = state["messages"]

    # Find the last user message
    user_input = "Unknown input"
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_input = cast(str, m.content)
            break

    # --- Fast-path: deterministic check (no LLM call) ---
    fast_verdict = _fast_path_verdict(user_input)
    if fast_verdict == "SAFE":
        logger.debug("GUARDRAIL: fast-path SAFE")
        return {
            "guardrail_verdict": "SAFE",
            "user_question": user_input,
            **_semantic_route(user_input),
        }
    if fast_verdict == "UNSAFE":
        logger.warning("GUARDRAIL: fast-path UNSAFE: %s", user_input[:100])
        return {
            "guardrail_verdict": "UNSAFE",
            "output": (
                "🚫 **Process blocked by Security Policy.**\n"
                "Your request was flagged as unsafe or irrelevant "
                "to the public audit context."
            ),
        }

    # --- Slow-path: LLM check for ambiguous queries ---
    logger.debug("GUARDRAIL: ambiguous input — falling back to LLM check")
    safety_prompt = load_prompt("guardrail_input.md")
    llm = get_llm("guardrail_model", timeout=30)

    chain = (
        ChatPromptTemplate.from_messages(
            [("system", safety_prompt), ("human", "{input}")]
        )
        | llm
    )

    response = chain.invoke({"input": user_input})
    verdict = cast(str, response.content).strip().upper()

    if "UNSAFE" in verdict:
        logger.warning("Input blocked by guardrail: %s", user_input[:100])
        return {
            "guardrail_verdict": "UNSAFE",
            "output": (
                "🚫 **Process blocked by Security Policy.**\n"
                "Your request was flagged as unsafe or irrelevant "
                "to the public audit context."
            ),
        }

    return {
        "guardrail_verdict": "SAFE",
        "user_question": user_input,
        **_semantic_route(user_input),
    }


@observe_node(event_type="GUARDRAIL")
def guardrail_output(state: AgentState) -> dict[str, str]:
    """
    Sanitize output before returning to user using deterministic regex PII detection.

    Replaces the LLM-based output guardrail with pattern matching for:
    - CPF numbers (000.000.000-00)
    - Email addresses
    - Brazilian phone numbers
    - API keys (sk-...)
    - Credit card numbers

    When execution never ran (abort path after max critic retries), builds an
    informative message from the last critic evaluation instead of returning the
    opaque "No output generated." string.

    Args:
        state: Current agent state containing output to validate.

    Returns:
        Updated state with PII-redacted output.
    """
    raw_output = state.get("output")

    if not raw_output:
        # Execution never ran — critic rejected max_retries times.
        # Surface the last critic evaluation so the user understands why.
        evaluation = state.get("evaluation") or "No evaluation recorded."
        iterations = state.get("iterations", 0)
        raw_output = (
            "The agent was unable to generate a valid response after "
            f"{iterations} attempt(s).\n\n"
            "Last reviewer feedback:\n"
            f"{evaluation}\n\n"
            "Please rephrase your question or provide additional context."
        )
        logger.warning(
            "Abort path reached after %d iterations. Last evaluation: %s",
            iterations,
            evaluation[:200],
        )

    sanitized = _redact_pii(raw_output)

    if sanitized != raw_output:
        logger.info("PII redacted from output")

    return {"output": sanitized}
