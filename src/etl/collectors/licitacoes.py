"""
Tenders (Licitações) Collector.

Collects public tender/procurement data from the TCE API.
"""

import calendar
import json
import logging
from typing import Any, Iterator

from .base import BaseCollector

logger = logging.getLogger(__name__)


class TendersCollector(BaseCollector):
    """Collector for public tender (licitação) data."""

    def run(self, municipio_id: str, year: int) -> int:
        """
        Run the tender collection for a municipality and year.

        Returns:
            Total number of records collected.
        """
        total = 0
        logger.info(">>> Starting Licitações (Data Set)")

        for batch in self.fetch_by_month(municipio_id, year):
            saved = self.save(batch, municipio_id, year)
            total += saved

        logger.info("Licitações completed: %d records.", total)
        return total

    def fetch_by_month(
        self, municipio_id: str, year: int
    ) -> Iterator[list[dict[str, Any]]]:
        """
        Fetch tender data month by month.

        Yields:
            Lists of tender records for each month.
        """
        for month in range(1, 13):
            last_day = calendar.monthrange(int(year), month)[1]
            start_date = f"{year}-{month:02d}-01"
            end_date = f"{year}-{month:02d}-{last_day}"
            date_range = f"{start_date}_{end_date}"

            params = {
                "codigo_municipio": municipio_id,
                "data_realizacao_autuacao_licitacao": date_range,
            }
            url = f"{self.client.BASE_URL}/licitacoes"

            logger.info("Fetching Licitações: %s", date_range)
            data = self.client.fetch_json(url, params)

            if data:
                if isinstance(data, list):
                    yield data
                elif isinstance(data, dict):
                    yield data.get("data", [])

    def save(
        self, batch_data: list[dict[str, Any]], municipio_id: str, year: int
    ) -> int:
        """
        Save tender records to the database.

        Returns:
            Number of records saved.
        """
        conn = self.db_manager.get_raw_connection()
        cursor = conn.cursor()
        count = 0

        try:
            for item in batch_data:
                lic_id = f"{municipio_id}_{item.get('numero_licitacao')}_{year}"
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO licitacoes (
                        id, municipio_id, numero_licitacao, numero_processo,
                        objeto_licitacao, modalidade_licitacao,
                        data_realizacao_licitacao, valor_estimado,
                        situacao_licitacao, exercicio_orcamento, raw_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
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
                    ),
                )
                count += 1

            conn.commit()
        finally:
            conn.close()

        return count
