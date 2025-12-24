import logging
import time

import requests

from src.config import get_settings

logger = logging.getLogger(__name__)


class TCEClient:
    def __init__(self):
        self.settings = get_settings()
        self.BASE_URL = self.settings.get("tce", {}).get("base_url")
        self.SIM_BASE_URL = self.settings.get("tce", {}).get("sim_base_url")

    def fetch_json(self, url, params, timeout=20, retries=3):
        for attempt in range(retries):
            try:
                response = requests.get(url, params=params, timeout=timeout)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}/{retries}): {e}")
                time.sleep(1 * (attempt + 1))

        logger.error(f"Failed to fetch {url} after {retries} attempts.")
        return None
