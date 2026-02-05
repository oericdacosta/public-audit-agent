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

    DESPESAS = ("/balancete_despesa_orcamentaria", APIBase.DEFAULT)
    RECEITAS = ("/balancete_receita_orcamentaria", APIBase.DEFAULT)
    LICITACOES = ("/licitacoes", APIBase.DEFAULT)
    MUNICIPIOS = ("/municipios", APIBase.DEFAULT)
    ORGAOS = ("/orgaos", APIBase.DEFAULT)
    UNIDADES_ORCAMENTARIAS = ("/unidades_orcamentarias", APIBase.DEFAULT)
    FUNCOES = ("/funcoes", APIBase.DEFAULT)
    ORDENADORES = ("/ordenadores", APIBase.DEFAULT)

    CONTAS_BANCARIAS = ("/contas_bancarias", APIBase.DEFAULT)
    PROGRAMAS = ("/programas", APIBase.DEFAULT)
    PROJETOS_ATIVIDADES = ("/despesa_projeto_atividade", APIBase.DEFAULT)
    ORCAMENTO_RECEITA = ("/orcamento_receita", APIBase.DEFAULT)

    path: str
    base: APIBase

    def __init__(self, path: str, base: APIBase) -> None:
        """Initialize endpoint with path and base URL type."""
        self.path = path
        self.base = base
