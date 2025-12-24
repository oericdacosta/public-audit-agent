import logging
import os

import docker

from src.config import get_settings

logger = logging.getLogger(__name__)


class DockerSandbox:
    def __init__(self):
        self.settings = get_settings()
        try:
            self.image = self.settings["sandbox"]["image"]
        except KeyError as e:
            raise ValueError("Missing 'sandbox.image' in config.yaml") from e

        self.client = docker.from_env()
        self._ensure_image()

    def _ensure_image(self):
        try:
            self.client.images.get(self.image)
        except docker.errors.ImageNotFound:
            logger.info(f"Pulling image {self.image}...")
            self.client.images.pull(self.image)

    def execute(self, code: str, timeout: int = 30) -> str:
        """
        Executes python code in an ephemeral docker container using a mounted script.
        """
        try:
            shim_path = os.path.join(os.path.dirname(__file__), "shim.py")
            with open(shim_path, "r") as f:
                shim_code = f.read()

            full_code = shim_code + "\n\n" + code

            network_name = os.environ.get("DOCKER_NETWORK_NAME", None)
            mcp_host = os.environ.get("MCP_HOST", "host.docker.internal")
            mcp_port = os.environ.get("MCP_PORT", "8000")

            create_kwargs = {
                "image": self.image,
                "command": ["python", "/tmp/script.py"],
                "environment": {"MCP_HOST": mcp_host, "MCP_PORT": mcp_port},
                "mem_limit": "512m",
                "detach": True,  # Return container object
            }

            if network_name:
                create_kwargs["network"] = network_name
            else:
                create_kwargs["extra_hosts"] = {"host.docker.internal": "host-gateway"}
                create_kwargs["network_mode"] = "host"

            container = self.client.containers.create(**create_kwargs)

            try:
                import io
                import tarfile

                tar_stream = io.BytesIO()
                with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                    tar_data = full_code.encode("utf-8")
                    tarinfo = tarfile.TarInfo(name="script.py")
                    tarinfo.size = len(tar_data)
                    tar.addfile(tarinfo, io.BytesIO(tar_data))
                tar_stream.seek(0)

                container.put_archive("/tmp", tar_stream)

                container.start()
                container.wait()
                logs = container.logs()

                return logs.decode("utf-8")

            finally:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

        except docker.errors.ContainerError as e:
            return f"Execution Error: {str(e)}"
        except Exception as e:
            return f"System Error: {str(e)}"
