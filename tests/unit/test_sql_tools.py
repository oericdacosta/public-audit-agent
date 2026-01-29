"""
Tests for SQL tools module.

Tests the security validations, query sanitization,
and database tool functions.
"""

import pytest
from unittest.mock import patch, Mock


class TestSanitizeQuery:
    """Test suite for _sanitize_query function."""

    def test_removes_single_line_comments(self):
        """Should remove -- style comments."""
        from src.tools.sql import _sanitize_query

        query = "SELECT * FROM users -- this is a comment"
        result = _sanitize_query(query)
        assert "--" not in result
        assert "comment" not in result

    def test_removes_multi_line_comments(self):
        """Should remove /* */ style comments."""
        from src.tools.sql import _sanitize_query

        query = "SELECT /* hidden */ * FROM users"
        result = _sanitize_query(query)
        assert "/*" not in result
        assert "hidden" not in result

    def test_normalizes_whitespace(self):
        """Should normalize excessive whitespace."""
        from src.tools.sql import _sanitize_query

        query = "SELECT  *   FROM    users"
        result = _sanitize_query(query)
        assert "  " not in result


class TestValidateSqlSafety:
    """Test suite for validate_sql_safety function."""

    def test_rejects_non_select_queries(self):
        """Should reject queries that don't start with SELECT."""
        from src.tools.sql import validate_sql_safety

        is_safe, error = validate_sql_safety("DELETE FROM users")
        assert is_safe is False
        assert "SELECT" in error

    def test_rejects_drop_keyword(self):
        """Should reject queries containing DROP."""
        from src.tools.sql import validate_sql_safety

        is_safe, error = validate_sql_safety("SELECT * FROM users; DROP TABLE users")
        assert is_safe is False

    def test_rejects_insert_keyword(self):
        """Should reject queries containing INSERT."""
        from src.tools.sql import validate_sql_safety

        is_safe, error = validate_sql_safety("INSERT INTO users VALUES (1)")
        assert is_safe is False

    def test_rejects_update_keyword(self):
        """Should reject queries containing UPDATE."""
        from src.tools.sql import validate_sql_safety

        is_safe, error = validate_sql_safety("UPDATE users SET name = 'x'")
        assert is_safe is False

    def test_allows_valid_select(self):
        """Should allow valid SELECT queries."""
        from src.tools.sql import validate_sql_safety

        is_safe, error = validate_sql_safety("SELECT * FROM users WHERE id = 1")
        assert is_safe is True
        assert error == ""

    def test_rejects_multiple_statements(self):
        """Should reject queries with multiple statements."""
        from src.tools.sql import validate_sql_safety

        is_safe, error = validate_sql_safety("SELECT 1; SELECT 2")
        assert is_safe is False
        assert "Multiple" in error


class TestEnsureLimit:
    """Test suite for _ensure_limit function."""

    def test_adds_limit_when_missing(self):
        """Should add LIMIT clause when not present."""
        from src.tools.sql import _ensure_limit

        query = "SELECT * FROM users"
        result = _ensure_limit(query, 100)
        assert "LIMIT 100" in result

    def test_preserves_existing_limit(self):
        """Should not modify query with existing LIMIT."""
        from src.tools.sql import _ensure_limit

        query = "SELECT * FROM users LIMIT 10"
        result = _ensure_limit(query, 100)
        assert "LIMIT 10" in result
        assert "LIMIT 100" not in result


class TestQuerySql:
    """Test suite for query_sql function."""

    def test_rejects_unsafe_query(self):
        """Should return error for unsafe queries."""
        from src.tools.sql import query_sql

        result = query_sql("DROP TABLE users")
        assert "Error" in result

    def test_executes_safe_query(self, patch_db):
        """Should execute valid SELECT queries."""
        from src.tools.sql import query_sql

        result = query_sql("SELECT * FROM despesas")
        assert isinstance(result, list)
        assert len(result) == 2


class TestListTables:
    """Test suite for list_tables function."""

    def test_returns_table_list(self, patch_db):
        """Should return list of table names."""
        from src.tools.sql import list_tables

        result = list_tables()
        assert "despesas" in result
        assert "receitas" in result


class TestDescribeTable:
    """Test suite for describe_table function."""

    def test_returns_schema_for_existing_table(self, patch_db):
        """Should return DDL for existing table."""
        from src.tools.sql import describe_table

        result = describe_table("despesas")
        assert "CREATE TABLE" in result

    def test_returns_error_for_missing_table(self, patch_db):
        """Should return error message for non-existent table."""
        from src.tools.sql import describe_table

        patch_db.get_start_schema.return_value = {}
        result = describe_table("nonexistent")
        assert "not found" in result
