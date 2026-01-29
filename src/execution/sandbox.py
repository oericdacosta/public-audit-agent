"""
Docker Sandbox.

Executes Python code in isolated Docker containers for safety.
"""

import io
import logging
import os
import tarfile
from pathlib import Path
from typing import Optional

import docker

from src.config import get_settings
from src.exceptions import ConfigurationError, SandboxError

logger = logging.getLogger(__name__)


class DockerSandbox:
    """
    Executes Python code in ephemeral Docker containers.
    
    Provides isolation for running untrusted code with
    network access to the MCP server.
    """

    def __init__(self) -> None:
        """Initialize the Docker sandbox with configured image."""
        settings = get_settings()
        try:
            self.image = settings["sandbox"]["image"]
        except KeyError as e:
            raise ConfigurationError(
                "Missing configuration key",
                details="'sandbox.image' not found in config.yaml"
            ) from e

        self.client = docker.from_env()
        self._ensure_image()

    def _ensure_image(self) -> None:
        """Ensure the Docker image is available locally."""
        try:
            self.client.images.get(self.image)
        except docker.errors.ImageNotFound:
            logger.info("Pulling image %s...", self.image)
            self.client.images.pull(self.image)

    def execute(self, code: str, timeout: int = 30) -> str:
        """
        Execute Python code in an ephemeral Docker container.
        
        Args:
            code: Python code to execute.
            timeout: Maximum execution time in seconds.
        
        Returns:
            Output from code execution or error message.
        """
        try:
            # Load and prepend shim code
            shim_path = Path(__file__).parent / "shim.py"
            shim_code = shim_path.read_text(encoding="utf-8")
            full_code = shim_code + "\n\n" + code

            # Get network configuration from environment
            network_name = os.environ.get("DOCKER_NETWORK_NAME")
            mcp_host = os.environ.get("MCP_HOST", "host.docker.internal")
            mcp_port = os.environ.get("MCP_PORT", "8000")

            create_kwargs: dict = {
                "image": self.image,
                "command": ["python", "/tmp/script.py"],
                "environment": {"MCP_HOST": mcp_host, "MCP_PORT": mcp_port},
                "mem_limit": "512m",
                "detach": True,
            }

            if network_name:
                create_kwargs["network"] = network_name
            else:
                create_kwargs["extra_hosts"] = {"host.docker.internal": "host-gateway"}
                create_kwargs["network_mode"] = "host"

            container = self.client.containers.create(**create_kwargs)

            try:
                # Create tar archive with script
                tar_stream = io.BytesIO()
                with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                    tar_data = full_code.encode("utf-8")
                    tarinfo = tarfile.TarInfo(name="script.py")
                    tarinfo.size = len(tar_data)
                    tar.addfile(tarinfo, io.BytesIO(tar_data))
                tar_stream.seek(0)

                container.put_archive("/tmp", tar_stream)
                container.start()
                container.wait(timeout=timeout)
                logs = container.logs()

                return logs.decode("utf-8")

            finally:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

        except docker.errors.ContainerError as e:
            return f"Execution Error: {e}"
        except docker.errors.APIError as e:
            raise SandboxError("Docker API error", details=str(e)) from e
        except Exception as e:
            return f"System Error: {e}"
