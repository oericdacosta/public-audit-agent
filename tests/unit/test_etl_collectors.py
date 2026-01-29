"""
Unit tests for the ETL collectors base module.
"""

from unittest.mock import MagicMock

import pytest


class TestBaseCollector:
    """Tests for base collector functionality."""

    def test_base_collector_importable(self) -> None:
        """Should be able to import the base collector module."""
        from src.etl.collectors import base

        assert base is not None

    def test_base_collector_is_abstract(self) -> None:
        """BaseCollector should be abstract."""
        from src.etl.collectors.base import BaseCollector

        # Can't instantiate directly because it's abstract
        with pytest.raises(TypeError):
            BaseCollector(MagicMock(), MagicMock())  # type: ignore

    def test_base_collector_requires_run_method(self) -> None:
        """BaseCollector subclasses must implement run method."""
        from src.etl.collectors.base import BaseCollector

        class IncompleteCollector(BaseCollector):
            pass

        with pytest.raises(TypeError):
            IncompleteCollector(MagicMock(), MagicMock())  # type: ignore

    def test_base_collector_stores_dependencies(self) -> None:
        """Complete subclass should store db_manager and client."""
        from src.etl.collectors.base import BaseCollector

        class CompleteCollector(BaseCollector):
            def run(self, municipio_id: str, year: int) -> int:
                return 0

        mock_db = MagicMock()
        mock_client = MagicMock()
        collector = CompleteCollector(mock_db, mock_client)

        assert collector.db_manager is mock_db
        assert collector.client is mock_client
