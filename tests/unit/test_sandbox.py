"""
Unit tests for the execution sandbox module.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.exceptions import ConfigurationError


class TestDockerSandbox:
    """Tests for DockerSandbox class."""

    @patch("src.execution.sandbox.docker")
    @patch("src.execution.sandbox.get_settings")
    def test_initializes_with_config_image(
        self, mock_settings: MagicMock, mock_docker: MagicMock
    ) -> None:
        """Should initialize with image from config."""
        mock_settings.return_value = {"sandbox": {"image": "test-image:latest"}}
        mock_docker.from_env.return_value.images.get.return_value = MagicMock()

        from src.execution.sandbox import DockerSandbox

        sandbox = DockerSandbox()
        assert sandbox.image == "test-image:latest"

    @patch("src.execution.sandbox.docker")
    @patch("src.execution.sandbox.get_settings")
    def test_raises_config_error_for_missing_image(
        self, mock_settings: MagicMock, mock_docker: MagicMock
    ) -> None:
        """Should raise ConfigurationError when sandbox.image is missing."""
        mock_settings.return_value = {}

        from src.execution.sandbox import DockerSandbox

        with pytest.raises(ConfigurationError):
            DockerSandbox()

    @patch("src.execution.sandbox.docker")
    @patch("src.execution.sandbox.get_settings")
    def test_pulls_image_if_not_found(
        self, mock_settings: MagicMock, mock_docker: MagicMock
    ) -> None:
        """Should pull image if not found locally."""
        import docker.errors

        mock_settings.return_value = {"sandbox": {"image": "test:latest"}}
        mock_client = MagicMock()
        mock_client.images.get.side_effect = docker.errors.ImageNotFound("not found")
        mock_docker.from_env.return_value = mock_client
        mock_docker.errors = docker.errors

        from src.execution.sandbox import DockerSandbox

        DockerSandbox()
        mock_client.images.pull.assert_called_once_with("test:latest")


class TestSandboxExecute:
    """Tests for sandbox execute method."""

    @patch("src.execution.sandbox.docker")
    @patch("src.execution.sandbox.get_settings")
    def test_executes_code_in_container(
        self, mock_settings: MagicMock, mock_docker: MagicMock
    ) -> None:
        """Should execute code in a Docker container."""
        mock_settings.return_value = {"sandbox": {"image": "test:latest"}}
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.logs.return_value = b"Hello, World!\n"
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = MagicMock()
        mock_docker.from_env.return_value = mock_client

        from src.execution.sandbox import DockerSandbox

        sandbox = DockerSandbox()
        result = sandbox.execute("print('Hello, World!')")

        assert "Hello, World!" in result
        mock_container.start.assert_called_once()
        mock_container.remove.assert_called()

    @patch("src.execution.sandbox.docker")
    @patch("src.execution.sandbox.get_settings")
    def test_returns_error_on_container_error(
        self, mock_settings: MagicMock, mock_docker: MagicMock
    ) -> None:
        """Should return error message on container error."""
        import docker.errors

        mock_settings.return_value = {"sandbox": {"image": "test:latest"}}
        mock_client = MagicMock()
        mock_client.images.get.return_value = MagicMock()
        mock_client.containers.create.side_effect = docker.errors.ContainerError(
            container=MagicMock(),
            exit_status=1,
            command="test",
            image="test:latest",
            stderr="Error",
        )
        mock_docker.from_env.return_value = mock_client
        mock_docker.errors = docker.errors

        from src.execution.sandbox import DockerSandbox

        sandbox = DockerSandbox()
        result = sandbox.execute("print('test')")

        assert "Execution Error" in result
