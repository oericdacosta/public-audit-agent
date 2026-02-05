"""
Unit tests for ETL Main module.
"""

from unittest.mock import MagicMock, patch

from src.etl.main import process_task


class TestEtlMain:
    """Tests for ETL main orchestration logic."""

    @patch("src.etl.main.get_sync_status")
    @patch("src.etl.main.update_sync_status")
    def test_process_task_skips_if_completed(
        self, mock_update: MagicMock, mock_get_status: MagicMock
    ) -> None:
        """Should skip processing if status is already COMPLETED."""
        mock_get_status.return_value = "COMPLETED"
        db_manager = MagicMock()
        collector = MagicMock()

        result = process_task(db_manager, "162", 2025, "endpoints", collector)

        assert "Skipped" in result
        mock_update.assert_not_called()
        collector.run.assert_not_called()

    @patch("src.etl.main.get_sync_status")
    @patch("src.etl.main.update_sync_status")
    def test_process_task_runs_if_not_completed(
        self, mock_update: MagicMock, mock_get_status: MagicMock
    ) -> None:
        """Should run collector if status is not COMPLETED."""
        mock_get_status.return_value = None
        db_manager = MagicMock()
        collector = MagicMock()
        collector.run.return_value = 100

        result = process_task(db_manager, "162", 2025, "endpoints", collector)

        assert "Finished" in result
        assert "100" in result
        # Starts and Completes
        assert mock_update.call_count == 2
        collector.run.assert_called_once_with("162", 2025)

    @patch("src.etl.main.get_sync_status")
    @patch("src.etl.main.update_sync_status")
    def test_process_task_handles_failure(
        self, mock_update: MagicMock, mock_get_status: MagicMock
    ) -> None:
        """Should catch exceptions and update status to FAILED."""
        mock_get_status.return_value = None
        db_manager = MagicMock()
        collector = MagicMock()
        collector.run.side_effect = Exception("API Error")

        result = process_task(db_manager, "162", 2025, "endpoints", collector)

        assert "Failed" in result
        # Starts and Fail
        assert mock_update.call_count == 2
        mock_update.assert_any_call(db_manager, "162", 2025, "endpoints", "FAILED")
