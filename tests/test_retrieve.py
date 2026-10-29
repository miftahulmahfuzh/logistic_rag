from kirana_rag.ingest.chunk import Chunk
from kirana_rag.retrieve import Index, tokenize


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


def test_spelling_and_plural_variants_collapse():
    assert tokenize("utilisation") == tokenize("utilization") == tokenize("utilisations")
    assert tokenize("trucks") == tokenize("truck")


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
