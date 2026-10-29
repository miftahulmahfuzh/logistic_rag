"""BM25 retrieval over chunk header+text. Index is rebuilt in memory on every run."""

import re
import sys
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from . import config
from .ingest.chunk import Chunk
from .ingest.pipeline import list_doc_ids, load_chunks

STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the this to was were "
    "what which who whom how many much did do does with".split()
)
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")
_TOKEN = re.compile(r"\d+\.\d+|[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, `8,420` -> `8420`, alphanumeric tokens (decimals kept whole), stopwords out.

    No stemming on purpose: the baseline records that as a hypothesis for failures.
    """
    text = _THOUSANDS.sub("", text.lower())
    return [t for t in _TOKEN.findall(text) if t not in STOPWORDS]


@dataclass
class Hit:
    chunk: Chunk
    score: float
    rank: int


class Index:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.bm25 = BM25Okapi([tokenize(c.indexed_text) for c in chunks]) if chunks else None

    def search(self, query: str, k: int = config.DEFAULT_TOP_K) -> list[Hit]:
        if self.bm25 is None:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:k]
        return [Hit(self.chunks[i], float(scores[i]), r + 1) for r, i in enumerate(order)]


def load_index(doc_id: str | None = None) -> Index:
    """Index one ingested document, or every document in the cache."""
    ids = [doc_id] if doc_id else list_doc_ids()
    chunks = [c for d in ids for c in load_chunks(d)]
    return Index(chunks)


def main(argv: list[str]) -> None:
    """Debug path: python -m kirana_rag.retrieve "question" [-k 5] [--doc ID]."""
    args = list(argv)
    k = int(args.pop(args.index("-k") + 1)) if "-k" in args else config.DEFAULT_TOP_K
    if "-k" in args:
        args.remove("-k")
    doc = args.pop(args.index("--doc") + 1) if "--doc" in args else None
    if "--doc" in args:
        args.remove("--doc")
    query = " ".join(args)
    print(f"tokens: {tokenize(query)}")
    for h in load_index(doc).search(query, k):
        c = h.chunk
        label = c.caption or c.section
        print(
            f"{h.rank}. {h.score:7.3f}  {c.chunk_id:8} p{'-'.join(map(str, c.pages))} {c.type:6} {label[:60]}"
        )


if __name__ == "__main__":
    main(sys.argv[1:])
