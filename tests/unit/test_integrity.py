"""
Behavioral tests for the integrity check node (src/agents/integrity.py).

Tests algorithmic gap detection — no LLM calls, no database:
- _is_empty_result: detects empty/null-only SQL outputs
- _all_result_cols_are_always_null: detects all-null column results
- check_result_integrity: full node behavior (empty result, all-null, normal)
"""

import json
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from src.agents.integrity import (
    _all_result_cols_are_always_null,
    _is_empty_result,
    check_result_integrity,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(**kwargs):
    """Build a minimal AgentState dict for testing."""
    base = {
        "messages": [HumanMessage(content="Qual o total de despesas em 2024?")],
        "iterations": 0,
    }
    base.update(kwargs)
    return base


def _json(obj) -> str:
    return json.dumps(obj)


# ---------------------------------------------------------------------------
# _is_empty_result
# ---------------------------------------------------------------------------


class TestIsEmptyResult:
    """Detects empty or null-only SQL outputs."""

    def test_empty_list(self):
        assert _is_empty_result(_json([])) is True

    def test_empty_dict(self):
        assert _is_empty_result("{}") is True

    def test_empty_string(self):
        assert _is_empty_result("") is True

    def test_null_literal(self):
        assert _is_empty_result("null") is True

    def test_empty_nested_list(self):
        assert _is_empty_result("[[]]") is True

    def test_list_of_all_null_values(self):
        rows = [{"valor": None, "nome": None}]
        assert _is_empty_result(_json(rows)) is True

    def test_single_row_with_values(self):
        rows = [{"total": 1234567.89}]
        assert _is_empty_result(_json(rows)) is False

    def test_multiple_rows_with_values(self):
        rows = [{"total": 100}, {"total": 200}]
        assert _is_empty_result(_json(rows)) is False

    def test_row_with_mixed_null_and_value(self):
        rows = [{"valor": None, "nome": "Prefeitura"}]
        assert _is_empty_result(_json(rows)) is False

    def test_whitespace_only(self):
        assert _is_empty_result("   ") is True

    def test_invalid_json_treated_as_not_empty(self):
        # Non-parseable output → cannot confirm empty → safe default
        assert _is_empty_result("not valid json") is False


# ---------------------------------------------------------------------------
# _all_result_cols_are_always_null
# ---------------------------------------------------------------------------


class TestAllResultColsAreAlwaysNull:
    """Detects when every selected column is tagged always_null in YAML."""

    def test_empty_list_returns_false(self):
        # Empty result is handled by _is_empty_result, not this check
        assert _all_result_cols_are_always_null(_json([])) is False

    def test_invalid_json_returns_false(self):
        assert _all_result_cols_are_always_null("not json") is False

    def test_all_cols_in_always_null_index(self):
        rows = [{"valor_contrato": 0, "numero_contrato": "X"}]
        always_null_index = {"fct_licitacoes": {"valor_contrato", "numero_contrato"}}
        with patch(
            "src.agents.integrity._load_always_null_index",
            return_value=always_null_index,
        ):
            assert _all_result_cols_are_always_null(_json(rows)) is True

    def test_some_cols_not_in_always_null_index(self):
        rows = [{"valor_pago": 500.0, "nome_orgao": "Saúde"}]
        always_null_index = {"fct_despesas": {"valor_pago"}}
        with patch(
            "src.agents.integrity._load_always_null_index",
            return_value=always_null_index,
        ):
            # nome_orgao is not always_null → not all cols are null
            assert _all_result_cols_are_always_null(_json(rows)) is False

    def test_no_always_null_cols_in_index(self):
        rows = [{"valor_pago": 100.0}]
        with patch(
            "src.agents.integrity._load_always_null_index",
            return_value={},
        ):
            assert _all_result_cols_are_always_null(_json(rows)) is False


# ---------------------------------------------------------------------------
# check_result_integrity (node)
# ---------------------------------------------------------------------------


class TestCheckResultIntegrity:
    """Full node: routes gap detection based on output content."""

    def test_empty_output_sets_gap(self):
        state = _state(output=_json([]))
        result = check_result_integrity(state)
        assert result["data_gap_detected"] is True
        assert result["gap_reason"] == "empty_result"
        assert result["gap_context"] is not None

    def test_null_output_sets_gap(self):
        state = _state(output="null")
        result = check_result_integrity(state)
        assert result["data_gap_detected"] is True
        assert result["gap_reason"] == "empty_result"

    def test_normal_output_no_gap(self):
        rows = [{"total_despesas": 1_000_000.0}]
        state = _state(output=_json(rows))
        with patch(
            "src.agents.integrity._load_always_null_index",
            return_value={},
        ):
            result = check_result_integrity(state)
        assert result["data_gap_detected"] is False
        assert result["gap_reason"] is None
        assert result["gap_context"] is None

    def test_all_null_cols_sets_data_unavailable_gap(self):
        # Values are non-null (0), but columns are tagged always_null in YAML.
        # _is_empty_result won't trigger; _all_result_cols_are_always_null will.
        rows = [{"valor_contrato": 0, "numero_contrato": "N/A"}]
        always_null_index = {"fct_licitacoes": {"valor_contrato", "numero_contrato"}}
        state = _state(output=_json(rows))
        with patch(
            "src.agents.integrity._load_always_null_index",
            return_value=always_null_index,
        ):
            result = check_result_integrity(state)
        assert result["data_gap_detected"] is True
        assert result["gap_reason"] == "data_unavailable"
        assert result["gap_alternative"] is not None

    def test_missing_output_in_state(self):
        state = _state()  # no 'output' key
        result = check_result_integrity(state)
        assert result["data_gap_detected"] is True
        assert result["gap_reason"] == "empty_result"

    def test_gap_context_contains_reason(self):
        state = _state(output=_json([]))
        result = check_result_integrity(state)
        assert "empty_result" in result["gap_context"]

    def test_gap_context_contains_detail(self):
        state = _state(output=_json([]))
        result = check_result_integrity(state)
        assert result["gap_detail"] is not None
        assert len(result["gap_detail"]) > 10
