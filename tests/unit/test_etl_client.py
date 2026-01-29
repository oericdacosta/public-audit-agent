"""
Unit tests for the ETL client module.
"""

from unittest.mock import MagicMock, patch

import requests

from src.etl.client import TCEClient


class TestTCEClient:
    """Tests for TCEClient class."""

    def test_initializes_with_config(self) -> None:
        """Should initialize with URLs from config."""
        with patch("src.etl.client.get_settings") as mock_settings:
            mock_settings.return_value = {
                "tce": {
                    "base_url": "https://api.tce.ce.gov.br",
                    "sim_base_url": "https://sim.tce.ce.gov.br",
                }
            }
            client = TCEClient()
            assert client.BASE_URL == "https://api.tce.ce.gov.br"
            assert client.SIM_BASE_URL == "https://sim.tce.ce.gov.br"


class TestFetchJson:
    """Tests for fetch_json method."""

    @patch("src.etl.client.get_settings")
    @patch("src.etl.client.requests.get")
    def test_returns_json_on_success(
        self, mock_get: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Should return parsed JSON on successful request."""
        mock_settings.return_value = {"tce": {}}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_get.return_value = mock_response

        client = TCEClient()
        result = client.fetch_json("http://example.com", {})
        assert result == {"data": "test"}

    @patch("src.etl.client.get_settings")
    @patch("src.etl.client.requests.get")
    def test_returns_none_on_404(
        self, mock_get: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Should return None on 404 response."""
        mock_settings.return_value = {"tce": {}}
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        client = TCEClient()
        result = client.fetch_json("http://example.com/notfound", {})
        assert result is None

    @patch("src.etl.client.get_settings")
    @patch("src.etl.client.requests.get")
    def test_returns_none_on_request_exception(
        self, mock_get: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Should return None after retries on request exception."""
        mock_settings.return_value = {"tce": {}}
        mock_get.side_effect = requests.exceptions.ConnectionError("Failed")

        client = TCEClient()
        result = client.fetch_json("http://example.com", {}, retries=1)
        assert result is None
