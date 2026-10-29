"""Dense embeddings of chunks: a small local model, computed once per ingest and cached as .npy."""

import sys
from typing import Protocol

import numpy as np

from .ingest.chunk import Chunk
from .ingest.pipeline import doc_dir

MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = (
    "Represent this sentence for searching relevant passages: "  # bge's query instruction
)
FILE = "embeddings.npy"


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


def _unit(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


class FastEmbedder:
    """BAAI/bge-small-en-v1.5 through fastembed (ONNX, CPU). The model downloads on first use."""

    def __init__(self) -> None:
        from fastembed import TextEmbedding

        self.model = TextEmbedding(MODEL)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return _unit(np.array(list(self.model.embed(texts)), dtype=np.float32))

    def embed_query(self, text: str) -> np.ndarray:
        return _unit(
            np.array(next(iter(self.model.embed([QUERY_PREFIX + text]))), dtype=np.float32)
        )


def load_or_build(doc_id: str, chunks: list[Chunk], embedder: Embedder) -> np.ndarray:
    """Chunk vectors for one document: read `embeddings.npy` when it is current, else embed and save.

    Chunks are embedded as `header + text`, the same string BM25 indexes.
    """
    folder = doc_dir(doc_id)
    path = folder / FILE
    chunks_file = folder / "chunks.jsonl"
    if path.exists() and path.stat().st_mtime >= chunks_file.stat().st_mtime:
        vectors = np.load(path)
        if len(vectors) == len(chunks):
            return vectors
    vectors = embedder.embed_documents([c.indexed_text for c in chunks])
    np.save(path, vectors)
    return vectors


def try_embedder() -> Embedder | None:
    """The default embedder, or None with a one-line warning when the model cannot be loaded."""
    try:
        return FastEmbedder()
    except Exception as e:  # noqa: BLE001 - offline first run, missing wheel, ...: never crash
        print(
            f"warning: dense model unavailable ({type(e).__name__}); using BM25 only",
            file=sys.stderr,
        )
        return None
