"""
Result Integrity Check Node.

Data-driven gap detection based on actual query results and YAML metadata.
No keyword matching, no SQL regex parsing, no intent detection.

Prevention happens upstream via the compact schema ([NULL:API não retorna] annotations).
This node is the post-execution safety net: detects empty results and all-null
monetary columns using YAML metadata alone.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from src.schemas.state import AgentState
from src.utils.logger import observe_node

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# YAML always-null index — loaded once at module level
# ---------------------------------------------------------------------------

# Cache: {table_name: set of column names with data_quality=always_null}
_ALWAYS_NULL_INDEX: Optional[dict[str, set[str]]] = None


def _load_always_null_index() -> dict[str, set[str]]:
    """
    Load columns tagged data_quality=always_null from dbt mart YAML files.

    Returns {table_name: {column_name, ...}}.
    Cached after first load.
    """
    global _ALWAYS_NULL_INDEX
    if _ALWAYS_NULL_INDEX is not None:
        return _ALWAYS_NULL_INDEX

    import yaml

    index: dict[str, set[str]] = {}
    mart_dir = (
        Path(__file__).resolve().parent.parent.parent / "dbt" / "models" / "marts"
    )
    if not mart_dir.exists():
        _ALWAYS_NULL_INDEX = index
        return index

    for yml_file in mart_dir.glob("*.yml"):
        try:
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            for model in data.get("models", []):
                table_name = model.get("name", "")
                if not table_name:
                    continue
                null_cols: set[str] = set()
                for col in model.get("columns", []):
                    col_name = col.get("name", "")
                    if (
                        col_name
                        and (col.get("meta") or {}).get("data_quality") == "always_null"
                    ):
                        null_cols.add(col_name)
                if null_cols:
                    index[table_name] = null_cols
        except Exception:
            pass

    _ALWAYS_NULL_INDEX = index
    return index


# ---------------------------------------------------------------------------
# Flat set of all always-null column names across all tables
# ---------------------------------------------------------------------------


def _flat_always_null() -> frozenset[str]:
    """Return flat set of all always-null column names (across all tables)."""
    index = _load_always_null_index()
    return frozenset(col for cols in index.values() for col in cols)


# ---------------------------------------------------------------------------
# Result checks
# ---------------------------------------------------------------------------

_EMPTY_LITERALS = frozenset({"[]", "{}", "", "null", "[[]]", "[{}]"})


def _is_empty_result(output: str) -> bool:
    """Return True if the SQL result contains no rows."""
    stripped = output.strip()
    if stripped in _EMPTY_LITERALS:
        return True
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return len(parsed) == 0 or all(
                isinstance(r, dict) and all(v is None for v in r.values())
                for r in parsed
            )
    except Exception:
        pass
    return False


def _all_result_cols_are_always_null(output: str) -> bool:
    """
    Return True if every column in the result is tagged always_null in YAML.

    Detects the case where the query returned rows but all selected columns
    are known to be always NULL in the TCE-CE source (e.g. columns tagged
    data_quality: always_null in the YAML) — produces results that cannot answer
    any value-related question.
    """
    try:
        parsed = json.loads(output)
        if not isinstance(parsed, list) or not parsed:
            return False
        result_cols = set(parsed[0].keys())
        if not result_cols:
            return False
        null_cols = _flat_always_null()
        return result_cols.issubset(null_cols)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main integrity check node
# ---------------------------------------------------------------------------


@observe_node(event_type="TOOL_CALL")
def check_result_integrity(state: AgentState) -> dict[str, Any]:
    """
    Data-driven gap detection — no LLM, no keyword matching, no SQL parsing.

    Check 1: empty result     → gap_reason "empty_result"
    Check 2: all result cols are always_null in YAML → gap_reason "data_unavailable"

    Prevention (always-null columns disclosed to the SQL-generating LLM via
    [NULL:API não retorna] annotations in the compact schema) runs upstream.
    This node handles cases that slip through or require post-execution confirmation.
    """
    output = state.get("output") or ""

    gap_detected = False
    gap_reason: Optional[str] = None
    gap_detail: Optional[str] = None
    gap_alternative: Optional[str] = None

    if _is_empty_result(output):
        gap_detected = True
        gap_reason = "empty_result"
        gap_detail = "A consulta não retornou registros para os filtros aplicados."

    elif _all_result_cols_are_always_null(output):
        gap_detected = True
        gap_reason = "data_unavailable"
        gap_detail = (
            "A consulta retornou registros, mas todos os campos selecionados "
            "estão sempre nulos na fonte TCE-CE — a API não fornece esses valores."
        )
        gap_alternative = (
            "Para valores de referência, consulte "
            "fct_licitacoes.valor_estimado ou "
            "fct_licitacoes_risco.valor_total_vencedor."
        )

    if gap_detected:
        logger.info(
            "INTEGRITY: gap detected — reason=%s detail=%s", gap_reason, gap_detail
        )

    gap_context: Optional[str] = None
    if gap_detected and gap_reason:
        lines = [
            "**Gap Detection Context** (gerado algoritmicamente — não ignorar):",
            f"- gap_reason: {gap_reason}",
        ]
        if gap_detail:
            lines.append(f"- gap_detail: {gap_detail}")
        if gap_alternative:
            lines.append(f"- gap_alternative: {gap_alternative}")
        gap_context = "\n".join(lines)

    return {
        "data_gap_detected": gap_detected,
        "gap_reason": gap_reason,
        "gap_detail": gap_detail,
        "gap_alternative": gap_alternative,
        "gap_context": gap_context,
    }
