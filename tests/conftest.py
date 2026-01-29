"""
Shared pytest fixtures for public-audit-agent tests.

This module provides reusable fixtures for mocking LLMs,
configurations, and agent states.
"""

from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def mock_settings():
    """Mock application settings for testing."""
    return {
        "agent": {
            "analyst_model": "gpt-4o",
            "critic_model": "gpt-4o-mini",
            "fiscal_model": "gpt-4o",
            "planner_model": "gpt-4o",
            "guardrail_model": "gpt-4o-mini",
            "max_retries": 3,
            "recursion_limit": 30,
        },
        "database": {
            "path": ":memory:",
            "query_timeout": 30,
        },
        "sandbox": {
            "image": "python:3.12-slim",
            "timeout": 30,
            "memory_limit": "512m",
        },
    }


@pytest.fixture
def mock_llm_response():
    """Mock LLM response for testing agents."""
    mock = Mock()
    mock.content = "SELECT SUM(valor_pago) FROM despesas LIMIT 10"
    return mock


@pytest.fixture
def sample_agent_state():
    """Sample AgentState for testing workflow nodes."""
    from langchain_core.messages import HumanMessage

    return {
        "messages": [HumanMessage(content="Qual o total de despesas em 2024?")],
        "guardrail_verdict": None,
        "plan": None,
        "sql_query": None,
        "code": "",
        "output": "",
        "error": None,
        "evaluation": None,
        "iterations": 0,
    }


@pytest.fixture
def mock_db_manager():
    """Mock DatabaseManager for testing database tools."""
    mock = Mock()
    mock.execute_query.return_value = [
        {"id": 1, "valor_pago": 1000.00},
        {"id": 2, "valor_pago": 2000.00},
    ]
    mock.get_all_tables.return_value = ["licitacoes", "despesas", "receitas"]
    mock.get_start_schema.return_value = {
        "despesas": "CREATE TABLE despesas (id TEXT, valor_pago REAL)"
    }
    return mock


@pytest.fixture
def patch_settings(mock_settings):
    """Patch get_settings to return mock configuration."""
    with patch("src.config.get_settings", return_value=mock_settings):
        yield mock_settings


@pytest.fixture
def patch_db(mock_db_manager):
    """Patch _get_db to return mock database manager."""
    with patch("src.tools.sql._get_db", return_value=mock_db_manager):
        yield mock_db_manager
