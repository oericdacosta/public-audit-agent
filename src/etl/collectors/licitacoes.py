"""
Tenders (Licitações) Collector.

Collects public tender/procurement data from the TCE API.
Uses MonthlyCollector base class with sequential mode for API stability.
"""

import calendar
import json
import logging
from typing import cast

from src.etl.endpoints import Endpoint

from .base import MonthlyCollector

logger = logging.getLogger(__name__)


class TendersCollector(MonthlyCollector):
    """
    Collector for public tender (licitação) data.

    Uses sequential month fetching for API stability (max_workers=1 equivalent).
    """

    collector_name = "Licitações"

    def _fetch_month(self, municipio_id: str, year: int, month: int) -> list[dict]:
        """Fetch tender data for a single month."""
        last_day = calendar.monthrange(int(year), month)[1]
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-{last_day}"
        date_range = f"{start_date}_{end_date}"

        params = {
            "codigo_municipio": municipio_id,
            "data_realizacao_autuacao_licitacao": date_range,
        }
        url = self.client.build_url(Endpoint.LICITACOES)

        data = self.client.fetch_json(url, params)
        if not data:
            return []

        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return cast(list[dict], data.get("data", []))

        return []

    def _save_all(self, all_records: list[dict], municipio_id: str, year: int) -> int:
        """Save all records to database in one bulk insert."""
        if not all_records:
            return 0

        records = []
        for item in all_records:
            lic_id = f"{municipio_id}_{item.get('numero_licitacao', 'unknown')}_{year}"
            records.append(
                (
                    lic_id,
                    municipio_id,
                    item.get("numero_licitacao"),
                    item.get("numero_processo_licitatorio"),
                    item.get("objeto_licitacao"),
                    item.get("modalidade_licitacao"),
                    item.get("data_realizacao_licitacao"),
                    item.get("valor_licitacao"),
                    item.get("situacao_licitacao"),
                    str(year),
                    json.dumps(item),
                )
            )

        columns = [
            "id",
            "municipio_id",
            "numero_licitacao",
            "numero_processo",
            "objeto_licitacao",
            "modalidade_licitacao",
            "data_realizacao_licitacao",
            "valor_estimado",
            "situacao_licitacao",
            "exercicio_orcamento",
            "raw_data",
        ]

        update_columns = [
            "objeto_licitacao",
            "valor_estimado",
            "situacao_licitacao",
            "raw_data",
        ]

        return self.bulk_upsert("licitacoes", columns, records, update_columns)
