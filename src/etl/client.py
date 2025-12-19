import requests
import time
import logging

logger = logging.getLogger(__name__)

class TCEClient:
    BASE_URL = "https://api-dados-abertos.tce.ce.gov.br"
    SIM_BASE_URL = "https://api.tce.ce.gov.br/index.php/sim/1_0"

    def fetch_json(self, url, params, timeout=20, retries=3):
        for attempt in range(retries):
            try:
                response = requests.get(url, params=params, timeout=timeout)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt+1}/{retries}): {e}")
                time.sleep(1 * (attempt + 1))
        
        logger.error(f"Failed to fetch {url} after {retries} attempts.")
        return None
