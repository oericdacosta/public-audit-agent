"""
Schema Introspection.

Provides utilities for inspecting database schema and table definitions.
"""

import unicodedata
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.etl.db_manager import DatabaseManager


class SchemaIntrospector:
    """
    Provides schema introspection capabilities for DuckDB.

    Extracts and searches table definitions and column information.
    """

    def __init__(self, db_manager: "DatabaseManager") -> None:
        """
        Initialize with a database manager.

        Args:
            db_manager: DatabaseManager instance for database access.
        """
        self._db_manager = db_manager

    def get_all_tables(self) -> list[str]:
        """
        Get list of all table names in the database.

        Returns:
            List of table names.
        """
        with self._db_manager.get_connection() as conn:
            rows = conn.execute("SHOW TABLES").fetchall()
            return [row[0] for row in rows]

    def get_schema(self, limit_tables: Optional[list[str]] = None) -> dict[str, str]:
        """
        Get schema definitions for tables.

        Reconstructs CREATE TABLE statements from DuckDB's DESCRIBE output.

        Args:
            limit_tables: Optional list of table names to filter.

        Returns:
            Dictionary mapping table names to DDL strings.
        """
        with self._db_manager.get_connection() as conn:
            tables = self.get_all_tables()
            if limit_tables:
                tables = [t for t in tables if t in limit_tables]

            schemas = {}
            for table in tables:
                columns = conn.execute(f"DESCRIBE {table}").fetchall()
                cols_ddl = []
                for col in columns:
                    name = col[0]
                    dtype = col[1]
                    is_null = col[2]
                    key = col[3]

                    part = f"{name} {dtype}"
                    if key == "PRI":
                        part += " PRIMARY KEY"
                    elif is_null == "NO":
                        part += " NOT NULL"
                    cols_ddl.append(part)

                ddl = (
                    f"CREATE TABLE {table} (\n    " + ",\n    ".join(cols_ddl) + "\n);"
                )
                schemas[table] = ddl
            return schemas

    def search(self, keyword: str) -> dict[str, str]:
        """
        Search table names and schema definitions for a keyword.

        Performs accent-insensitive, case-insensitive search.

        Args:
            keyword: Search term.

        Returns:
            Dictionary of matching table names to their DDL.
        """
        schemas = self.get_schema()
        results: dict[str, str] = {}
        keyword_norm = self._normalize_text(keyword)

        for name, sql in schemas.items():
            name_norm = self._normalize_text(name)
            sql_norm = self._normalize_text(sql)

            if keyword_norm in name_norm or keyword_norm in sql_norm:
                results[name] = sql

        return results

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text for accent-insensitive comparison."""
        if not text:
            return ""
        return "".join(
            c
            for c in unicodedata.normalize("NFD", text)
            if unicodedata.category(c) != "Mn"
        ).lower()
