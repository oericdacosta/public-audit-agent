"""
Generic Collector.

Handles extraction for standard endpoints that don't require custom processing logic.
Uses Endpoint properties for deterministic data extraction.
"""

import asyncio
import logging
from typing import Any

from src.etl.client import AsyncTCEClient
from src.etl.db_manager import DatabaseManager
from src.etl.endpoints import Endpoint
from src.etl.utils.masking import sanitize_record

logger = logging.getLogger(__name__)

# Endpoints that don't require any parameters (global lookups)
NO_PARAMS_ENDPOINTS = frozenset({Endpoint.MUNICIPIOS, Endpoint.FUNCOES})

# Endpoints that cannot be bulk-extracted (require specific search params)
SKIP_ENDPOINTS = frozenset(
    {Endpoint.NEGOCIANTES}  # Requires 'nome_negociante' search parameter
)

# Endpoints that require pagination parameters and looping
PAGINATED_ENDPOINTS = frozenset(
    {
        # Detailed transactional data
        Endpoint.TALOES_RECEITAS,
        Endpoint.TALOES_EXTRAS,
        Endpoint.NOTAS_FISCAIS,
        Endpoint.NOTAS_PAGAMENTOS,
        Endpoint.ITENS_NOTAS_FISCAIS,
        Endpoint.AGENTES_PUBLICOS,
        Endpoint.LIQUIDACOES,
        # Dimension/lookup tables (accepts pagination params)
        Endpoint.UNIDADES_ORCAMENTARIAS,
    }
)


class GenericCollector:
    """
    A universal collector for standard TCE endpoints.

    Fetches data from the API and loads it directly into the target table,
    using the Endpoint's response_key for deterministic extraction.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        client: AsyncTCEClient,
        endpoint: Endpoint,
    ) -> None:
        """
        Initialize the generic collector.

        Args:
            db_manager: Database manager instance
            client: HTTP Client instance
            endpoint: The Endpoint definition (path, base, table_name, response_key)
        """
        self.db_manager = db_manager
        self.client = client
        self.endpoint = endpoint

    def _build_base_params(self, municipality_id: str, year: int) -> dict[str, str]:
        """Build base request parameters."""
        if self.endpoint in NO_PARAMS_ENDPOINTS:
            return {}

        return {
            "codigo_municipio": municipality_id,
            "exercicio_orcamento": f"{year}00",
        }

    def _extract_records(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Extract the list of records from API response.

        Uses the Endpoint's response_key for deterministic extraction,
        with fallback patterns for compatibility.
        """
        if not data:
            return []

        # Primary: Use the endpoint's defined response_key
        if self.endpoint.response_key and self.endpoint.response_key in data:
            content = data[self.endpoint.response_key]
            if isinstance(content, list):
                return content
            elif isinstance(content, dict):
                return [content]

        # Fallback: Common API response patterns
        for key in ["data", "rows", "_content"]:
            if key in data:
                content = data[key]
                if isinstance(content, list):
                    return content
                elif isinstance(content, dict):
                    # Handle nested data structure (e.g. data -> data list)
                    if "data" in content and isinstance(content["data"], list):
                        return content["data"]
                    if "rows" in content and isinstance(content["rows"], list):
                        return content["rows"]
                    return [content]

        # Fallback: rsp._content pattern
        if "rsp" in data and isinstance(data["rsp"], dict):
            content = data["rsp"].get("_content")
            if isinstance(content, list):
                return content
            elif isinstance(content, dict):
                return [content]

        # Last resort: single-key wrapper
        if len(data) == 1:
            single_value = list(data.values())[0]
            if isinstance(single_value, list):
                return single_value

        return []

    async def _fetch_first_page(
        self, municipality_id: str, year: int, page_size: int = 100
    ) -> tuple[list[dict], int]:
        """Fetch first page and extract total count from response.

        Returns:
            Tuple of (records, total). total=0 means API didn't provide count.
        """
        params = self._build_base_params(municipality_id, year)
        params["quantidade"] = str(page_size)
        params["deslocamento"] = "0"

        data = await self.client.fetch(self.endpoint, params)
        if not data:
            return [], 0

        total = 0
        # Format A: {"rsp": {"_total": N, "_content": [...]}}
        if "rsp" in data and isinstance(data["rsp"], dict):
            total = int(data["rsp"].get("_total", 0))
        # Format B: {"data": {"total": N, "data": [...]}}
        elif "data" in data and isinstance(data["data"], dict):
            total = int(data["data"].get("total", 0))

        records = self._extract_records(data)
        return records, total

    async def _fetch_page(
        self,
        municipality_id: str,
        year: int,
        offset: int,
        page_size: int = 100,
    ) -> list[dict]:
        """Fetch a single page of paginated data."""
        params = self._build_base_params(municipality_id, year)
        params["quantidade"] = str(page_size)
        params["deslocamento"] = str(offset)

        data = await self.client.fetch(self.endpoint, params)
        if not data:
            return []
        return self._extract_records(data)

    def _augment_records(
        self, records: list[dict], municipality_id: str, year: int
    ) -> list[dict]:
        """Augment raw records with standard fields, IDs, and masking."""
        import json

        augmented = []
        for item in records:
            item_copy = item.copy()
            id_field = self._get_id_field(item)
            item_copy["id"] = f"{municipality_id}_{id_field}_{year}"
            item_copy["municipio_id"] = municipality_id
            item_copy["exercicio_orcamento"] = str(year)
            item_copy["raw_data"] = json.dumps(item)
            augmented.append(sanitize_record(item_copy, self.endpoint.table_name))
        return augmented

    async def _run_paginated(self, municipality_id: str, year: int) -> int:
        """
        Run collection with robust pagination and bulk save.

        Uses a sequential loop to guarantee data completeness, as async
        """
        page_size = 500
        all_records = []
        offset = 0

        # Loop until no more records are returned
        while True:
            # Fetch page
            page_records = await self._fetch_page(
                municipality_id, year, offset, page_size
            )

            if not page_records:
                break

            count = len(page_records)
            all_records.extend(page_records)

            logger.debug(
                "%s: fetched page size=%d offset=%d total_so_far=%d",
                self.endpoint.name,
                count,
                offset,
                len(all_records),
            )

            # Accessing next page
            offset += page_size

            # If no records returned, loop breaks at start of next iteration
            # or we can check here to avoid one extra request
            if not page_records:
                break

        logger.info(
            "%s: fetched %d records total. Saving...",
            self.endpoint.name,
            len(all_records),
        )

        if not all_records:
            return 0

        # Save all at once (Bulk Insert) to minimize DB lock contention
        augmented = await asyncio.to_thread(
            self._augment_records, all_records, municipality_id, year
        )
        await asyncio.to_thread(
            self.db_manager.load_data, self.endpoint.table_name, augmented
        )

        return len(all_records)

    def _get_id_field(self, record: dict) -> str:
        """Generate a unique identifier from record fields."""
        # Try common ID fields (transactional)
        for field in [
            "numero_talao_receita",
            "nu_talao_receita_tx",
            "numero_nota_fiscal",
            "numero_liquidacao",
            "codigo_agente",
            "numero_pagamento",
            # Dimension/lookup table fields
            "codigo_municipio",
            "codigo_funcao",
            "codigo_orgao",
            "codigo_unidade_orcamentaria",
            "codigo_ordenador",
            "numero_conta",
            "codigo_programa",
            "codigo_projeto_atividade",
            "codigo_receita",
        ]:
            if field in record:
                return str(record[field])
        # Fallback: hash of record
        import hashlib

        return hashlib.md5(  # noqa: S324
            str(sorted(record.items())).encode(), usedforsecurity=False
        ).hexdigest()[:12]

    async def run(self, municipality_id: str, year: int) -> int:
        """
        Execute collection for the configured endpoint.

        Args:
            municipality_id: The city code
            year: The fiscal year

        Returns:
            Count of records inserted
        """
        if self.endpoint in SKIP_ENDPOINTS:
            logger.debug("Skipping %s (requires search params)", self.endpoint.name)
            return 0

        if self.endpoint in PAGINATED_ENDPOINTS:
            return await self._run_paginated(municipality_id, year)

        # Non-paginated flow
        params = self._build_base_params(municipality_id, year)
        data = await self.client.fetch(self.endpoint, params)

        if not data:
            return 0

        records = self._extract_records(data)

        if not records:
            return 0

        augmented = await asyncio.to_thread(
            self._augment_records, records, municipality_id, year
        )
        await asyncio.to_thread(
            self.db_manager.load_data, self.endpoint.table_name, augmented
        )

        return len(records)
