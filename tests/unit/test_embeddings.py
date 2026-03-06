"""
Unit tests for semantic catalog and embedding utilities.

Tests cover pure-Python functions (no API calls) and graceful fallback
behavior when the embedding index is not available.
"""

import math
from unittest.mock import patch


class TestCosineSimilarity:
    """Tests for the cosine similarity math function."""

    def test_identical_vectors_return_one(self):
        from src.utils.embeddings import cosine_similarity

        v = [1.0, 0.0, 0.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-9

    def test_orthogonal_vectors_return_zero(self):
        from src.utils.embeddings import cosine_similarity

        assert abs(cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 1e-9

    def test_opposite_vectors_return_minus_one(self):
        from src.utils.embeddings import cosine_similarity

        assert abs(cosine_similarity([1.0, 0.0], [-1.0, 0.0]) - (-1.0)) < 1e-9

    def test_zero_vector_returns_zero(self):
        from src.utils.embeddings import cosine_similarity

        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_arbitrary_vectors(self):
        from src.utils.embeddings import cosine_similarity

        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        dot = 1 * 4 + 2 * 5 + 3 * 6  # 32
        na = math.sqrt(1 + 4 + 9)
        nb = math.sqrt(16 + 25 + 36)
        expected = dot / (na * nb)
        assert abs(cosine_similarity(a, b) - expected) < 1e-9


class TestAnalyzeQuestionFallback:
    """When the embedding index is missing, analyze_question returns safe defaults."""

    def test_returns_empty_list_and_false_when_index_missing(self):
        from src.utils.embeddings import _load_index, analyze_question

        _load_index.cache_clear()
        with patch("src.utils.embeddings.INDEX_PATH") as mock_path:
            mock_path.exists.return_value = False
            _load_index.cache_clear()
            tables, is_complex = analyze_question("qualquer pergunta")

        assert tables == []
        assert is_complex is False
        _load_index.cache_clear()


class TestLoadCatalog:
    """load_catalog reads dbt YML files and returns table metadata."""

    def test_returns_dict_with_known_tables(self):
        from src.utils.catalog import load_catalog

        catalog = load_catalog()
        assert isinstance(catalog, dict)
        # At minimum, mart tables created earlier should be present
        assert len(catalog) > 0

    def test_each_entry_has_required_keys(self):
        from src.utils.catalog import load_catalog

        catalog = load_catalog()
        for name, meta in catalog.items():
            assert "description" in meta, f"{name} missing description"
            assert "embed_text" in meta, f"{name} missing embed_text"
            assert name in meta["embed_text"], f"{name} not in its own embed_text"

    def test_augmented_tables_include_aliases(self):
        from src.utils.catalog import load_catalog

        catalog = load_catalog()
        if "agg_orcamento_por_funcao_ano" in catalog:
            text = catalog["agg_orcamento_por_funcao_ano"]["embed_text"]
            assert "LOA" in text or "orçamento" in text.lower()
