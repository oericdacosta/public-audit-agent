import os
from typing import Any, Dict

import yaml

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")


def load_config() -> Dict[str, Any]:
    """
    Loads the YAML configuration file from the project root.
    """
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Config file not found at {CONFIG_PATH}")

    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


try:
    _config = load_config()
except Exception as e:
    print(f"WARNING: Could not load config.yaml: {e}")
    _config = {}


def get_settings() -> Dict[str, Any]:
    return _config
