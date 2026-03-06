"""
Mart table catalog loader.

Reads dbt YML schema files from dbt/models/marts/ and builds rich text
descriptions for each table, suitable for embedding-based semantic search.
"""

import logging
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

MART_MODELS_PATH = Path(__file__).parent.parent.parent / "dbt" / "models" / "marts"

# Curated augmentations for tables that need extra aliases beyond their YML description.
# These bridge the gap between user vocabulary and dbt column/table naming.
_AUGMENTATIONS: dict[str, str] = {
    "agg_orcamento_por_funcao_ano": (
        "Aliases e termos equivalentes: LOA, orçamento previsto, dotação orçamentária, "
        "fixado, planejado, lei orçamentária anual, autorizado, previsto, "
        "quanto deveria ter sido gasto, meta de gasto, orçamento aprovado."
    ),
    "agg_data_quality": (
        "Aliases e termos equivalentes: qualidade dos dados, confiabilidade do dado, "
        "dado zerado, publicação pendente, dado inconsistente, zero suspeito, "
        "dado ainda não publicado, atraso de publicação TCE-CE."
    ),
    "fct_licitacoes_risco": (
        "Aliases e termos equivalentes: fraude em licitação, irregularidade, "
        "superfaturamento, suspeito, score de risco, dispensa irregular, "
        "sobrepreço, licitação deserta, único participante."
    ),
    "agg_resultado_fiscal_mensal": (
        "Aliases e termos equivalentes: superávit, déficit, saúde fiscal, "
        "equilíbrio orçamentário, receita versus despesa, situação financeira, "
        "balanço mensal, resultado primário."
    ),
    "brd_licitantes": (
        "Aliases e termos equivalentes: quem participou da licitação, "
        "empresa licitante, participante habilitado, CPF CNPJ licitante."
    ),
    "fct_contratos_fornecedores": (
        "Aliases e termos equivalentes: empresa contratada, CNPJ, fornecedor, "
        "contrato assinado, prestador de serviço."
    ),
}


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, dict]:
    """
    Load all mart table metadata from dbt YML schema files.

    Returns:
        dict mapping table_name -> {description, columns, embed_text}
        where embed_text is the rich string to be embedded by the model.
    """
    catalog: dict[str, dict] = {}

    yml_files = list(MART_MODELS_PATH.glob("*.yml"))
    if not yml_files:
        logger.warning("No YML files found in %s", MART_MODELS_PATH)
        return catalog

    for yml_path in yml_files:
        try:
            with open(yml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            logger.warning("Failed to parse %s: %s", yml_path.name, e)
            continue

        for model in data.get("models") or []:
            name: str = model.get("name", "")
            if not name:
                continue

            description: str = (model.get("description") or "").strip()
            columns: list[dict] = model.get("columns") or []

            # Build column summary — up to 12 most informative columns
            col_parts = []
            for col in columns[:12]:
                col_name = col.get("name", "")
                col_desc = (col.get("description") or "").strip()
                if col_name:
                    entry = f"{col_name} ({col_desc})" if col_desc else col_name
                    col_parts.append(entry)
            col_text = "; ".join(col_parts)

            # Build the rich embedding text
            lines = [
                f"Tabela: {name}",
                f"Finalidade: {description}",
            ]
            if col_text:
                lines.append(f"Colunas-chave: {col_text}")
            augmentation = _AUGMENTATIONS.get(name)
            if augmentation:
                lines.append(augmentation)

            embed_text = "\n".join(lines)

            catalog[name] = {
                "description": description,
                "columns": columns,
                "embed_text": embed_text,
            }

    logger.debug("Loaded catalog with %d mart tables", len(catalog))
    return catalog
