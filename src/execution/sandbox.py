"""
Docker Sandbox.

Executes Python code in isolated Docker containers for safety.
Uses a singleton with a persistent warm container to eliminate per-call
container creation overhead (~300ms savings).
"""

import io
import logging
import os
import tarfile
from pathlib import Path
from typing import ClassVar, Optional

import docker

from src.config import get_settings
from src.exceptions import ConfigurationError, SandboxError

logger = logging.getLogger(__name__)


class DockerSandbox:
    """
    Executes Python code using a persistent warm Docker container.

    A singleton container is kept alive between calls via `exec_run`,
    eliminating the ~300ms container create/start/destroy overhead per query.
    The warm container uses the same security constraints as ephemeral containers.
    """

    _instance: ClassVar[Optional["DockerSandbox"]] = None
    _warm_container: ClassVar[Optional[object]] = None

    def __init__(self) -> None:
        """Initialize the Docker sandbox with configured image."""
        settings = get_settings()
        try:
            self.image = settings["sandbox"]["image"]
        except KeyError as e:
            raise ConfigurationError(
                "Missing configuration key",
                details="'sandbox.image' not found in config.yaml",
            ) from e

        self.client = docker.from_env()
        self._ensure_image()

    @classmethod
    def get_instance(cls) -> "DockerSandbox":
        """Return the singleton DockerSandbox, creating it if necessary."""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._start_warm_container()
        return cls._instance

    def _ensure_image(self) -> None:
        """Ensure the Docker image is available locally."""
        try:
            self.client.images.get(self.image)
        except docker.errors.ImageNotFound:
            logger.info("Pulling image %s...", self.image)
            self.client.images.pull(self.image)

    def _build_container_kwargs(self, detach: bool = True) -> dict:
        """Build container creation kwargs with shared security options."""
        network_name = os.environ.get("DOCKER_NETWORK_NAME")
        mcp_host = os.environ.get("MCP_HOST", "host.docker.internal")
        mcp_port = os.environ.get("MCP_PORT", "8000")

        kwargs: dict = {
            "image": self.image,
            "environment": {"MCP_HOST": mcp_host, "MCP_PORT": mcp_port},
            "mem_limit": "512m",
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "user": "nobody",
            "detach": detach,
            "extra_hosts": {"host.docker.internal": "host-gateway"},
        }

        if network_name:
            kwargs["network"] = network_name
        else:
            kwargs["network_mode"] = "bridge"

        return kwargs

    def _start_warm_container(self) -> None:
        """Start a persistent container kept alive with `sleep infinity`."""
        try:
            kwargs = self._build_container_kwargs(detach=True)
            kwargs["command"] = ["sleep", "infinity"]
            DockerSandbox._warm_container = self.client.containers.run(**kwargs)
            cid = DockerSandbox._warm_container.id[:12]  # type: ignore
            logger.info("Warm sandbox container started: %s", cid)
        except Exception as e:
            logger.warning("Failed to start warm container: %s", e)
            DockerSandbox._warm_container = None

    def _copy_script(self, container: object, code: str) -> None:
        """Copy a Python script into /tmp/script.py inside the container."""
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            tar_data = code.encode("utf-8")
            tarinfo = tarfile.TarInfo(name="script.py")
            tarinfo.size = len(tar_data)
            tar.addfile(tarinfo, io.BytesIO(tar_data))
        tar_stream.seek(0)
        container.put_archive("/tmp", tar_stream)  # type: ignore  # nosec B108

    def execute(self, code: str, timeout: int = 30) -> str:
        """
        Execute Python code using the warm container (or ephemeral fallback).

        Args:
            code: Python code to execute.
            timeout: Maximum execution time in seconds.

        Returns:
            Output from code execution or error message.
        """
        # Load and prepend shim code
        shim_path = Path(__file__).parent / "shim.py"
        shim_code = shim_path.read_text(encoding="utf-8")
        full_code = shim_code + "\n\n" + code

        warm = DockerSandbox._warm_container

        # --- Warm container path (fast) ---
        if warm is not None:
            try:
                self._copy_script(warm, full_code)
                exit_code, output = warm.exec_run(  # type: ignore
                    ["python", "/tmp/script.py"],  # nosec B108
                    demux=False,
                )
                if isinstance(output, bytes):
                    result = output.decode("utf-8")
                else:
                    result = str(output)
                if exit_code != 0 and not result.strip():
                    return f"Execution Error: exit code {exit_code}"
                return result
            except Exception as e:
                logger.warning("Warm container exec failed, using ephemeral: %s", e)
                # Restart warm container for next call
                try:
                    warm.remove(force=True)  # type: ignore
                except Exception:
                    pass
                DockerSandbox._warm_container = None
                self._start_warm_container()

        # --- Ephemeral container fallback ---
        return self._execute_ephemeral(full_code, timeout)

    def _execute_ephemeral(self, full_code: str, timeout: int) -> str:
        """Execute in a freshly created container (fallback path)."""
        try:
            kwargs = self._build_container_kwargs(detach=True)
            kwargs["command"] = ["python", "/tmp/script.py"]  # nosec B108
            container = self.client.containers.create(**kwargs)

            try:
                self._copy_script(container, full_code)
                container.start()
                container.wait(timeout=timeout)
                logs: bytes = container.logs()
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

    @classmethod
    def cleanup(cls) -> None:
        """Stop and remove the warm container. Call on application shutdown."""
        if cls._warm_container is not None:
            try:
                cls._warm_container.remove(force=True)  # type: ignore
                logger.info("Warm sandbox container removed")
            except Exception as e:
                logger.warning("Failed to remove warm container: %s", e)
            finally:
                cls._warm_container = None
                cls._instance = None
