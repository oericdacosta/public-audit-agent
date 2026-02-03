"""
API Endpoints Definition.

Defines the available API endpoints and their corresponding base URLs.
"""

from enum import Enum


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
    """

    DESPESAS = ("/balancete_despesa_orcamentaria.json", APIBase.SIM)
    RECEITAS = ("/balancete_receita_orcamentaria.json", APIBase.SIM)
    LICITACOES = ("/licitacoes", APIBase.DEFAULT)
    MUNICIPIOS = ("/municipios", APIBase.SIM)
    ORGAOS = ("/orgaos", APIBase.SIM)
    UNIDADES_ORCAMENTARIAS = ("/unidades_orcamentarias", APIBase.SIM)
    FUNCOES = ("/funcoes", APIBase.SIM)
    ORDENADORES = ("/ordenadores", APIBase.SIM)
    CONTAS_BANCARIAS = ("/contas_bancarias", APIBase.SIM)

    path: str
    base: APIBase

    def __init__(self, path: str, base: APIBase) -> None:
        """Initialize endpoint with path and base URL type."""
        self.path = path
        self.base = base
