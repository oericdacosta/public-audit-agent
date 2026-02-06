"""
API Endpoints Definition.

Defines the available API endpoints and their corresponding base URLs,
table mappings, and response extraction keys.
"""

from enum import Enum
from typing import Optional


class APIBase(Enum):
    """Enumeration of available API base URLs."""

    DEFAULT = "base_url"
    SIM = "sim_base_url"


class Endpoint(Enum):
    """
    Enumeration of TCE API endpoints.

    Each endpoint is defined by:
    1. Relative path
    2. Base URL type
    3. Target table name (for database storage)
    4. Response key (for extracting data from API response)
    """

    # Financial Endpoints (Monthly)
    DESPESAS = (
        "/balancete_despesa_orcamentaria",
        APIBase.DEFAULT,
        "despesas",
        "balancete_despesa_orcamentaria",
    )
    RECEITAS = (
        "/balancete_receita_orcamentaria",
        APIBase.DEFAULT,
        "receitas",
        "balancete_receita_orcamentaria",
    )

    # Extra-Budgetary Endpoints (Monthly)
    BALANCETE_DESPESA_EXTRA = (
        "/balancete_despesa_extra_orcamentaria",
        APIBase.DEFAULT,
        "balancete_despesa_extra",
        "balancete_despesa_extra_orcamentaria",
    )
    BALANCETE_RECEITA_EXTRA = (
        "/balancete_receita_extra_orcamentaria",
        APIBase.DEFAULT,
        "balancete_receita_extra",
        "balancete_receita_extra_orcamentaria",
    )

    # Detailed Revenue Endpoints (Taloes)
    TALOES_RECEITAS = (
        "/taloes_receitas",
        APIBase.DEFAULT,
        "taloes_receitas",
        "taloes_receitas",
    )
    TALOES_EXTRAS = (
        "/taloes_extras",
        APIBase.DEFAULT,
        "taloes_extras",
        "taloes_extras",
    )

    # Procurement
    LICITACOES = (
        "/licitacoes",
        APIBase.DEFAULT,
        "licitacoes",
        "licitacoes",
    )

    # Dimension/Lookup Tables
    MUNICIPIOS = (
        "/municipios",
        APIBase.DEFAULT,
        "municipios",
        "municipios",
    )
    ORGAOS = (
        "/orgaos",
        APIBase.DEFAULT,
        "orgaos",
        "orgaos",
    )
    UNIDADES_ORCAMENTARIAS = (
        "/unidades_orcamentarias",
        APIBase.DEFAULT,
        "unidades_orcamentarias",
        "unidades_orcamentarias",
    )
    FUNCOES = (
        "/funcoes",
        APIBase.DEFAULT,
        "funcoes",
        "funcoes",
    )
    ORDENADORES = (
        "/ordenadores",
        APIBase.DEFAULT,
        "ordenadores",
        "ordenadores",
    )
    CONTAS_BANCARIAS = (
        "/contas_bancarias",
        APIBase.DEFAULT,
        "contas_bancarias",
        "contas_bancarias",
    )
    PROGRAMAS = (
        "/programas",
        APIBase.DEFAULT,
        "programas",
        "programas",
    )
    PROJETOS_ATIVIDADES = (
        "/despesa_projeto_atividade",
        APIBase.DEFAULT,
        "orcamento_despesa",
        "despesa_projeto_atividade",
    )
    ORCAMENTO_RECEITA = (
        "/orcamento_receita",
        APIBase.DEFAULT,
        "orcamento_receita",
        "orcamento_receita",
    )

    # Endpoint properties
    path: str
    base: APIBase
    table_name: str
    response_key: Optional[str]

    def __init__(
        self,
        path: str,
        base: APIBase,
        table_name: str = "",
        response_key: Optional[str] = None,
    ) -> None:
        """Initialize endpoint with path, base URL, table name, and key."""
        self.path = path
        self.base = base
        self.table_name = table_name
        self.response_key = response_key
