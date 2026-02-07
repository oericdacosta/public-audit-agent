"""
Unit tests for ETL Main module.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from src.etl.main import process_task


class TestEtlMain:
    """Tests for ETL main orchestration logic."""

    @pytest.mark.asyncio
    async def test_process_task_skips_if_completed(self) -> None:
        """Should skip processing if status is already COMPLETED."""
        mock_metadata = MagicMock()
        mock_metadata.get_status.return_value = "COMPLETED"

        collector = MagicMock()

        result = await process_task(mock_metadata, "162", 2025, "endpoints", collector)

        assert "Skipped" in result
        mock_metadata.update_status.assert_not_called()
        collector.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_task_runs_if_not_completed(self) -> None:
        """Should run collector if status is not COMPLETED."""
        mock_metadata = MagicMock()
        mock_metadata.get_status.return_value = None

        collector = MagicMock()
        future = asyncio.Future()
        future.set_result(100)
        collector.run.return_value = future

        result = await process_task(mock_metadata, "162", 2025, "endpoints", collector)

        assert "Finished" in result
        assert "100" in result
        # Starts and Completes
        assert mock_metadata.update_status.call_count == 2
        mock_metadata.update_status.assert_any_call("162", 2025, "endpoints", "STARTED")
        mock_metadata.update_status.assert_called_with(
            "162", 2025, "endpoints", "COMPLETED", 100
        )
        collector.run.assert_called_once_with("162", 2025)

    @pytest.mark.asyncio
    async def test_process_task_handles_failure(self) -> None:
        """Should catch exceptions and update status to FAILED."""
        mock_metadata = MagicMock()
        mock_metadata.get_status.return_value = None

        collector = MagicMock()
        future = asyncio.Future()
        future.set_exception(Exception("API Error"))
        collector.run.return_value = future

        result = await process_task(mock_metadata, "162", 2025, "endpoints", collector)

        assert "Failed" in result
        # Starts and Fail
        assert mock_metadata.update_status.call_count == 2
        mock_metadata.update_status.assert_any_call("162", 2025, "endpoints", "FAILED")
