import numpy as np
import pytest

from kirana_rag import embed, retrieve
from kirana_rag.ingest.chunk import Chunk
from kirana_rag.retrieve import Index, rrf, tokenize


def _chunk(cid: str, text: str, page: int = 1) -> Chunk:
    return Chunk(
        cid, "d", [page], "text", "", "", [0, 0, 1, 1], text, header=f"[Doc | p{page} | text]"
    )


def test_tokenizer_strips_thousands_separators():
    assert "8420" in tokenize("Revenue was THB 8,420 million")
    assert "1.71" in tokenize("leverage of 1.71x") or "1.71x" in tokenize("leverage of 1.71x")
    assert tokenize("62,000 sqm, 1,234,567") == ["62000", "sqm", "1234567"]


def test_tokenizer_lowercases_drops_stopwords_keeps_decimals():
    assert tokenize("What is the OTD in November: 89.7%?") == ["otd", *tokenize("november"), "89.7"]


def test_uk_and_us_spelling_collapse():
    assert tokenize("utilisation") == tokenize("utilization") == ["utilization"]
    assert tokenize("Labour tonne") == ["labor", "ton"]


def test_default_mode_does_not_stem():
    assert tokenize("trucks") == ["trucks"]


def test_full_mode_stems_and_none_mode_keeps_spelling(monkeypatch):
    monkeypatch.setenv("KIRANA_NORMALISE", "full")
    assert tokenize("trucks") == tokenize("truck")
    assert tokenize("utilisations") == tokenize("utilization")
    monkeypatch.setenv("KIRANA_NORMALISE", "none")
    assert tokenize("utilisation") == ["utilisation"]


def test_numbers_are_not_stemmed():
    assert tokenize("8,420 1.71 q3 2025") == ["8420", "1.71", "q3", "2025"]


def test_us_query_finds_uk_spelled_chunk():
    idx = Index(
        [
            _chunk("a", "Warehouse utilisation by site", 1),
            _chunk("b", "Employees by country at year end", 2),
            _chunk("c", "Revenue by quarter", 3),
        ]
    )
    assert idx.search("utilization", k=1)[0].chunk.chunk_id == "a"


def test_ranking_on_toy_corpus():
    idx = Index(
        [
            _chunk("a", "Cold chain storage tariff per pallet", 1),
            _chunk("b", "Employees by country at year end", 2),
            _chunk("c", "Revenue by quarter 2025 in THB million", 3),
            _chunk("d", "Greenhouse gas emissions scope one", 4),
        ]
    )
    hits = idx.search("revenue per quarter", k=2)
    assert hits[0].chunk.chunk_id == "c" and hits[0].rank == 1
    assert hits[0].score >= hits[1].score


def test_number_query_matches_comma_formatted_text():
    idx = Index(
        [_chunk("a", "Net debt 2,310 million"), _chunk("b", "Other 1,000"), _chunk("c", "x y z")]
    )
    assert idx.search("2310", k=1)[0].chunk.chunk_id == "a"


def test_empty_index_returns_nothing():
    assert Index([]).search("anything") == []


class FakeEmbedder:
    """Deterministic stand-in for the dense model: words in the same concept group share a dimension."""

    CONCEPTS = (
        frozenset({"staff", "workforce", "colleagues", "employees"}),
        frozenset({"revenue", "turnover"}),
        frozenset({"gas"}),
    )

    def _vec(self, text: str) -> np.ndarray:
        words = set(text.lower().replace(",", " ").split())
        v = np.array([len(words & group) for group in self.CONCEPTS], dtype=np.float32)
        return v / np.linalg.norm(v) if v.any() else v

    def embed_documents(self, texts):
        return np.array([self._vec(t) for t in texts])

    def embed_query(self, text):
        return self._vec(text)


def _toy_hybrid(retriever: str = "hybrid") -> Index:
    chunks = [
        _chunk("a", "Our workforce stands at 1284 colleagues", 1),
        _chunk("b", "Greenhouse gas emissions scope one", 2),
        _chunk("c", "Cold chain storage tariff per pallet", 3),
    ]
    emb = FakeEmbedder()
    return Index(chunks, emb.embed_documents([c.indexed_text for c in chunks]), emb, retriever)


def test_hybrid_finds_a_paraphrase_that_bm25_cannot():
    query = "how many staff"  # shares no word with the chunk
    assert _toy_hybrid("bm25").search(query, k=3)[0].score == 0.0
    top = _toy_hybrid("hybrid").search(query, k=1)[0]
    assert top.chunk.chunk_id == "a"
    assert top.dense_rank == 1


def test_rrf_math_on_a_known_pair_of_rankings():
    fused = rrf([[0, 1, 2], [2, 0, 1]], k=60)
    assert fused[0] == pytest.approx(1 / 61 + 1 / 62)
    assert fused[1] == pytest.approx(1 / 62 + 1 / 63)
    assert fused[2] == pytest.approx(1 / 63 + 1 / 61)
    assert sorted(fused, key=lambda i: -fused[i]) == [0, 2, 1]


def test_hit_keeps_both_ranks_for_debugging():
    hits = _toy_hybrid().search("how many staff", k=3)
    assert all(h.bm25_rank and h.dense_rank for h in hits)
    assert hits[0].score > hits[1].score


def test_bm25_retriever_ignores_vectors():
    hits = _toy_hybrid("bm25").search("greenhouse emissions", k=1)
    assert hits[0].chunk.chunk_id == "b" and hits[0].dense_rank is None


def test_missing_model_falls_back_to_bm25(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(retrieve, "list_doc_ids", lambda: ["d"])
    monkeypatch.setattr(retrieve, "load_chunks", lambda d: [_chunk("a", "Revenue by quarter")])

    def broken():
        raise OSError("no network")

    monkeypatch.setattr(embed, "FastEmbedder", broken)
    index = retrieve.load_index()
    assert not index.hybrid and index.search("revenue", k=1)[0].chunk.chunk_id == "a"
    assert "BM25 only" in capsys.readouterr().err


def test_embeddings_are_cached_next_to_the_chunks(monkeypatch, tmp_path):
    monkeypatch.setattr(embed, "doc_dir", lambda d: tmp_path)
    (tmp_path / "chunks.jsonl").write_text("{}\n")
    chunks = [_chunk("a", "Revenue by quarter"), _chunk("b", "Employees by country")]
    first = embed.load_or_build("d", chunks, FakeEmbedder())
    assert (tmp_path / "embeddings.npy").exists()

    class Boom:
        def embed_documents(self, texts):
            raise AssertionError("must read the cache")

    assert np.array_equal(embed.load_or_build("d", chunks, Boom()), first)
