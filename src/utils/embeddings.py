"""
Semantic table selection using OpenAI embeddings and cosine similarity.

Replaces the hardcoded _DOMAIN_TABLE_MAP and _MULTI_STEP_KEYWORDS with
a pre-built vector index over dbt mart table descriptions.

Usage:
    # Build the index (run once, or after mart YML changes):
    uv run python scripts/index_catalog.py

    # At query time (called automatically by guardrail_input):
    selected_tables, is_complex = analyze_question("quanto foi gasto em educação?")

Index storage: data/catalog_embeddings.json
"""

import hashlib
import json
import logging
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

INDEX_PATH = Path(__file__).parent.parent.parent / "data" / "catalog_embeddings.json"
MANIFEST_PATH = Path(__file__).parent.parent.parent / "data" / "catalog_manifest.json"
MART_MODELS_PATH = Path(__file__).parent.parent.parent / "dbt" / "models" / "marts"

EMBEDDING_MODEL = "text-embedding-3-small"
INDEX_VERSION = "2.0"

# Phrases that represent complex, multi-step query patterns.
# Designed in Portuguese (the user's language) for maximum similarity.
# From ML design: 16 anchors across 6 categories.
COMPLEXITY_ANCHORS: list[str] = [
    # Year-over-year comparison
    "comparar gastos de 2023 com 2024 para identificar variação anual",
    "evolução dos gastos ao longo dos anos, crescimento ou redução ano a ano",
    "qual foi a variação percentual entre o ano anterior e o atual",
    # Budget vs actual (LOA)
    "quanto foi previsto no orçamento versus quanto foi efetivamente gasto ou arrecadado",  # noqa: E501
    "diferença entre dotação orçamentária aprovada e execução real da despesa",
    "receita abaixo da meta orçada, déficit de arrecadação em relação ao previsto",
    # Rankings
    "quais são os maiores gastadores, ranking das secretarias com maior despesa",
    "top cinco fornecedores com maior valor contratado, concentração de mercado",
    # Trends / historical evolution
    "tendência histórica da despesa em educação e saúde ao longo dos últimos anos",
    "série temporal mensal da receita arrecadada para identificar sazonalidade",
    # Multi-entity / cross-domain
    "comparar performance de múltiplas secretarias simultaneamente no mesmo período",
    "análise combinada de receitas e despesas para calcular resultado fiscal",
    "quais órgãos tiveram maior crescimento de gastos e quais tiveram redução",
    # Should-have-spent vs actually-spent / execution gaps
    "quanto deveria ter sido gasto em saúde mas não foi executado, saldo não utilizado",
    "percentual de execução do orçamento, valor empenhado mas não pago, restos a pagar",
    "secretaria com pior taxa de execução, baixo aproveitamento do orçamento disponível",  # noqa: E501
]

# Table always included when any spending-by-function table is selected
# (it doesn't semantically match user questions but is needed for data quality)
_ALWAYS_INCLUDE_WITH: dict[str, list[str]] = {
    "agg_despesas_por_funcao_ano": ["agg_data_quality"],
    "agg_orcamento_por_funcao_ano": ["agg_data_quality"],
}


# ---------------------------------------------------------------------------
# Math utilities (pure Python — no numpy dependency)
# ---------------------------------------------------------------------------


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two embedding vectors."""
    na, nb = _norm(a), _norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return _dot(a, b) / (na * nb)


# ---------------------------------------------------------------------------
# OpenAI embedding call
# ---------------------------------------------------------------------------


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a batch of texts using OpenAI text-embedding-3-small.
    Returns one vector per text.
    """
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


# ---------------------------------------------------------------------------
# Index building (offline, called by scripts/index_catalog.py)
# ---------------------------------------------------------------------------


def _file_sha256(path: Path) -> str:
    """Compute SHA-256 of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _anchors_hash() -> str:
    """Stable hash of the complexity anchor phrases."""
    joined = "\n".join(COMPLEXITY_ANCHORS)
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def build_index() -> None:
    """
    Build the embedding index from dbt mart YML files and save to disk.

    Loads the existing index if present, computes a per-file SHA-256,
    and only re-embeds tables whose YML changed (selective re-embedding).
    Also re-embeds complexity anchors if they changed.
    """
    from src.utils.catalog import load_catalog

    catalog = load_catalog()
    if not catalog:
        logger.error("Catalog is empty — no YML files found. Aborting.")
        return

    # Load existing index for selective re-embedding
    existing: dict = {}
    if INDEX_PATH.exists():
        with open(INDEX_PATH, encoding="utf-8") as f:
            existing = json.load(f)
    existing_tables: dict[str, dict] = {
        e["table_name"]: e for e in existing.get("tables", [])
    }

    # Compute current file hashes
    current_hashes: dict[str, str] = {}
    for yml_path in MART_MODELS_PATH.glob("*.yml"):
        current_hashes[yml_path.name] = _file_sha256(yml_path)

    existing_hashes: dict[str, str] = existing.get("manifest", {}).get("files", {})

    # Determine which tables need re-embedding (their YML file changed)
    changed_files = {
        f for f, h in current_hashes.items() if existing_hashes.get(f) != h
    }
    if changed_files:
        logger.info("Changed YML files detected: %s", changed_files)
        # Clear cache so catalog reloads from disk
        load_catalog.cache_clear()

    # Build table entry list
    table_entries: list[dict] = []
    texts_to_embed: list[str] = []
    indices_to_embed: list[int] = []

    for table_name, meta in catalog.items():
        embed_text = meta["embed_text"]
        # Check if this table needs re-embedding
        existing_entry = existing_tables.get(table_name)
        needs_embed = (
            existing_entry is None
            or existing_entry.get("text") != embed_text
            or any(
                table_name.replace(".", "_") in f or f.replace(".yml", "") in table_name
                for f in changed_files
            )
        )

        if needs_embed or existing_entry is None:
            entry: dict = {
                "table_name": table_name,
                "text": embed_text,
                "embedding": None,
            }
            table_entries.append(entry)
            texts_to_embed.append(embed_text)
            indices_to_embed.append(len(table_entries) - 1)
        else:
            table_entries.append(existing_entry)

    # Re-embed only what's needed for tables
    if texts_to_embed:
        logger.info("Embedding %d table(s)...", len(texts_to_embed))
        vectors = embed_texts(texts_to_embed)
        for idx, vector in zip(indices_to_embed, vectors, strict=False):
            table_entries[idx]["embedding"] = vector

    # Re-embed complexity anchors if they changed
    current_a_hash = _anchors_hash()
    existing_a_hash = existing.get("manifest", {}).get("anchors_hash", "")
    if current_a_hash != existing_a_hash:
        logger.info("Re-embedding %d complexity anchors...", len(COMPLEXITY_ANCHORS))
        anchor_vectors = embed_texts(COMPLEXITY_ANCHORS)
        anchor_entries = [
            {"phrase": phrase, "embedding": vec}
            for phrase, vec in zip(COMPLEXITY_ANCHORS, anchor_vectors, strict=False)
        ]
    else:
        anchor_entries = existing.get("complexity_anchors", [])

    index = {
        "version": INDEX_VERSION,
        "model": EMBEDDING_MODEL,
        "tables": table_entries,
        "complexity_anchors": anchor_entries,
        "manifest": {
            "files": current_hashes,
            "anchors_hash": current_a_hash,
            "template_version": INDEX_VERSION,
        },
    }

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = INDEX_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(index, f)
    tmp_path.rename(INDEX_PATH)

    logger.info(
        "Index saved: %d tables, %d anchors → %s",
        len(table_entries),
        len(anchor_entries),
        INDEX_PATH,
    )


# ---------------------------------------------------------------------------
# Freshness check — called automatically at agent startup
# ---------------------------------------------------------------------------


def ensure_index_fresh() -> None:
    """
    Check if the embedding index is up-to-date and rebuild only if stale.

    Compares SHA-256 of each mart YML file and the complexity anchors hash
    against the stored manifest. Re-embeds only changed entries (selective).
    Called once at AuditGraph.__init__ — no manual intervention needed.
    """
    if not INDEX_PATH.exists():
        logger.info("Embedding index not found — building for the first time...")
        build_index()
        _load_index.cache_clear()
        return

    try:
        with open(INDEX_PATH, encoding="utf-8") as f:
            existing = json.load(f)
        existing_hashes: dict[str, str] = existing.get("manifest", {}).get("files", {})
        existing_anchors_hash: str = existing.get("manifest", {}).get(
            "anchors_hash", ""
        )
    except Exception as e:
        logger.warning("Embedding index unreadable (%s) — rebuilding...", e)
        build_index()
        _load_index.cache_clear()
        return

    stale = (
        any(
            existing_hashes.get(p.name) != _file_sha256(p)
            for p in MART_MODELS_PATH.glob("*.yml")
        )
        or _anchors_hash() != existing_anchors_hash
    )

    if stale:
        logger.info("Embedding index stale — rebuilding...")
        build_index()
        _load_index.cache_clear()
    else:
        logger.debug("Embedding index is up-to-date")


# ---------------------------------------------------------------------------
# Index loading (cached for agent lifetime)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_index() -> Optional[dict]:
    """Load the pre-built embedding index from disk. Returns None if not found."""
    if not INDEX_PATH.exists():
        logger.warning(
            "Embedding index not found at %s. "
            "Run: uv run python scripts/index_catalog.py",
            INDEX_PATH,
        )
        return None
    try:
        with open(INDEX_PATH, encoding="utf-8") as f:
            return dict(json.load(f))
    except Exception as e:
        logger.warning("Failed to load embedding index: %s", e)
        return None


# ---------------------------------------------------------------------------
# Query-time semantic analysis
# ---------------------------------------------------------------------------


def analyze_question(
    question: str,
    top_k: int = 4,
    complexity_threshold: float = 0.62,
    min_score: float = 0.30,
) -> tuple[list[str], bool]:
    """
    Embed the user question and return (selected_tables, is_complex).

    Makes a single OpenAI API call (~150–300ms) to embed the question,
    then uses pre-computed table and anchor embeddings for instant lookup.

    Args:
        question: Raw user question text.
        top_k: Maximum number of tables to return (default 4).
        complexity_threshold: Cosine similarity threshold for complexity detection.
        min_score: Minimum similarity score to include a table (default 0.45).

    Returns:
        (selected_tables, is_complex): Table names list and complexity flag.
        Falls back to ([], False) if the index is not available.
    """
    index = _load_index()
    if index is None:
        return [], False

    table_entries: list[dict] = index.get("tables", [])
    anchor_entries: list[dict] = index.get("complexity_anchors", [])

    if not table_entries:
        return [], False

    # Single API call — embed the question once, use for both lookups
    try:
        q_vec = embed_texts([question])[0]
    except Exception as e:
        logger.warning("Embedding API call failed: %s", e)
        return [], False

    # --- Table selection ---
    scored: list[tuple[str, float]] = []
    for entry in table_entries:
        emb = entry.get("embedding")
        if not emb:
            continue
        score = cosine_similarity(q_vec, emb)
        if score >= min_score:
            scored.append((entry["table_name"], score))

    scored.sort(key=lambda x: x[1], reverse=True)
    selected = [name for name, _ in scored[:top_k]]

    # Post-processing: always co-include paired tables
    extras: set[str] = set()
    for table in selected:
        for extra in _ALWAYS_INCLUDE_WITH.get(table, []):
            extras.add(extra)
    # Append extras that aren't already in selected (up to hard cap of 6)
    for extra in extras:
        if extra not in selected and len(selected) < 6:
            selected.append(extra)

    # --- Complexity detection ---
    is_complex = False
    if anchor_entries:
        max_sim = max(
            cosine_similarity(q_vec, a["embedding"])
            for a in anchor_entries
            if a.get("embedding")
        )
        is_complex = max_sim >= complexity_threshold
        logger.debug(
            "Complexity check: max_sim=%.3f threshold=%.3f → %s",
            max_sim,
            complexity_threshold,
            is_complex,
        )

    logger.debug("Selected tables: %s | is_complex=%s", selected, is_complex)
    return selected, is_complex
