"""Retrieval over chunk header+text: BM25, fused with dense retrieval by RRF. BM25 is rebuilt in memory on every run."""

import os
import re
import sys
from dataclasses import dataclass

import numpy as np
import snowballstemmer
from rank_bm25 import BM25Okapi

from . import config, embed
from .embed import Embedder
from .ingest.chunk import Chunk
from .ingest.pipeline import list_doc_ids, load_chunks

RETRIEVERS = ("hybrid", "bm25")
STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the this to was were "
    "what which who whom how many much did do does with".split()
)
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")
_TOKEN = re.compile(r"\d+\.\d+|[a-z0-9]+")
_ISATION = re.compile(r"isation(s)?\b")
UK_TO_US = {
    "labour": "labor",
    "colour": "color",
    "centre": "center",
    "programme": "program",
    "organise": "organize",
    "favour": "favor",
    "behaviour": "behavior",
    "licence": "license",
    "tonne": "ton",
}
_STEMMER = snowballstemmer.stemmer("english")


def _normalise(token: str) -> str:
    """UK -> US spelling, then (mode full only) English Snowball stem. Tokens with a digit are left alone.

    KIRANA_NORMALISE=none|spelling|full (default spelling) exists for the ablation in eval/ITERATIONS.md.
    """
    mode = os.environ.get("KIRANA_NORMALISE", "spelling")
    if mode == "none" or any(ch.isdigit() for ch in token):
        return token
    token = UK_TO_US.get(token, _ISATION.sub(r"ization\1", token))
    return token if mode == "spelling" else _STEMMER.stemWord(token)


def tokenize(text: str) -> list[str]:
    """Lowercase, `8,420` -> `8420`, alphanumeric tokens (decimals kept whole), stopwords out,
    then UK->US spelling (and Snowball stemming in the `full` ablation mode); never for tokens with digits.

    Used for both the index and the query, so they always agree.
    """
    text = _THOUSANDS.sub("", text.lower())
    return [_normalise(t) for t in _TOKEN.findall(text) if t not in STOPWORDS]


RRF_K = 60  # the standard reciprocal-rank-fusion constant; not tuned


@dataclass
class Hit:
    chunk: Chunk
    score: float
    rank: int
    bm25_rank: int | None = None  # 1-based rank in each ranking, kept for debugging
    dense_rank: int | None = None


def _ranking(scores) -> list[int]:
    """Chunk indices best first; ties keep index order so results are deterministic."""
    return sorted(range(len(scores)), key=lambda i: (-scores[i], i))


def rrf(rankings: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    """Reciprocal rank fusion with equal weights: score(i) = sum over rankings of 1 / (k + rank)."""
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, i in enumerate(ranking, 1):
            fused[i] = fused.get(i, 0.0) + 1.0 / (k + rank)
    return fused


class Index:
    """BM25 over header+text, plus (when vectors and an embedder are given) dense retrieval fused by RRF."""

    def __init__(
        self,
        chunks: list[Chunk],
        vectors: np.ndarray | None = None,
        embedder: Embedder | None = None,
        retriever: str = "hybrid",
    ) -> None:
        self.chunks = chunks
        self.bm25 = BM25Okapi([tokenize(c.indexed_text) for c in chunks]) if chunks else None
        self.vectors, self.embedder = vectors, embedder
        self.retriever = retriever

    @property
    def hybrid(self) -> bool:
        return self.retriever == "hybrid" and self.vectors is not None and self.embedder is not None

    def search(self, query: str, k: int = config.DEFAULT_TOP_K) -> list[Hit]:
        if self.bm25 is None:
            return []
        bm25_scores = self.bm25.get_scores(tokenize(query))
        bm25_order = _ranking(bm25_scores)
        if not self.hybrid:
            return [
                Hit(self.chunks[i], float(bm25_scores[i]), r, bm25_rank=r)
                for r, i in enumerate(bm25_order[:k], 1)
            ]
        dense_scores = self.vectors @ self.embedder.embed_query(query)
        dense_order = _ranking(dense_scores)
        fused = rrf([bm25_order, dense_order])
        bm25_rank = {i: r for r, i in enumerate(bm25_order, 1)}
        dense_rank = {i: r for r, i in enumerate(dense_order, 1)}
        order = sorted(fused, key=lambda i: (-fused[i], i))[:k]
        return [
            Hit(self.chunks[i], fused[i], r, bm25_rank[i], dense_rank[i])
            for r, i in enumerate(order, 1)
        ]


def load_index(doc_id: str | None = None, retriever: str = "hybrid") -> Index:
    """Index one ingested document, or every document in the cache.

    `retriever` is `hybrid` (BM25 + dense) or `bm25`. If the dense model cannot be loaded the index
    falls back to BM25 with a warning.
    """
    if retriever not in RETRIEVERS:
        raise ValueError(f"unknown retriever {retriever!r}; use one of {RETRIEVERS}")
    ids = [doc_id] if doc_id else list_doc_ids()
    per_doc = [load_chunks(d) for d in ids]
    chunks = [c for cs in per_doc for c in cs]
    embedder = embed.try_embedder() if retriever == "hybrid" and chunks else None
    if embedder is None:
        return Index(chunks, retriever="bm25")
    vectors = np.concatenate([embed.load_or_build(d, cs, embedder) for d, cs in zip(ids, per_doc)])
    return Index(chunks, vectors, embedder, retriever)


def main(argv: list[str]) -> None:
    """Debug path: python -m kirana_rag.retrieve "question" [-k 8] [--doc ID] [--retriever bm25|hybrid]."""
    args = list(argv)

    def option(flag: str, default: str | None) -> str | None:
        if flag not in args:
            return default
        value = args.pop(args.index(flag) + 1)
        args.remove(flag)
        return value

    k = int(option("-k", str(config.DEFAULT_TOP_K)))
    doc = option("--doc", None)
    retriever = option("--retriever", "hybrid")
    query = " ".join(args)
    print(f"tokens: {tokenize(query)}")
    print("rank  score    bm25 dense  chunk    pages type   label")
    for h in load_index(doc, retriever).search(query, k):
        c = h.chunk
        label = c.caption or c.section
        print(
            f"{h.rank:>3}. {h.score:7.4f} {h.bm25_rank or '-':>5} {h.dense_rank or '-':>5}  "
            f"{c.chunk_id:8} p{'-'.join(map(str, c.pages))} {c.type:6} {label[:50]}"
        )


if __name__ == "__main__":
    main(sys.argv[1:])
