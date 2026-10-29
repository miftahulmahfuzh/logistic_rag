"""Fill `gold_chunks` in a question file from its `gold_text` strings and the ingested chunks.

A chunk is gold for a question when its text contains any of the question's gold_text strings (case-insensitive, pipes
and extra whitespace ignored, numbers matched as whole tokens). The retrieval or answers are never consulted. A string
that no chunk contains is reported as an ingestion loss; a question with no matching chunk gets no gold_chunks line.

Usage: uv run python scripts/resolve_gold_chunks.py eval/questions_holdout2.yaml <doc_id> [--write]
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kirana_rag.ingest.pipeline import load_chunks


def flat(text: str) -> str:
    return " ".join(text.replace("|", " ").lower().split())


def contains(chunk_text: str, snippet: str) -> bool:
    pattern = r"(?<![\w.,])" + re.escape(flat(snippet)) + r"(?![\w]|[.,]\d)"
    return re.search(pattern, flat(chunk_text)) is not None


def main(path: Path, doc_id: str, write: bool) -> None:
    chunks = load_chunks(doc_id)
    lines = path.read_text().splitlines()
    questions = yaml.safe_load(path.read_text())
    out, resolved = list(lines), {}
    for q in questions:
        if "gold_text" not in q or "gold_chunks" in q:
            continue
        ids: list[str] = []
        for snippet in q["gold_text"]:
            hit = [c.chunk_id for c in chunks if contains(c.indexed_text, snippet)]
            print(f"{q['id']}  {snippet!r:60} -> {hit or 'NOT FOUND (ingestion loss)'}")
            ids += [i for i in hit if i not in ids]
        if ids:
            resolved[q["id"]] = ids
    for qid, ids in resolved.items():
        start = next(i for i, ln in enumerate(out) if ln == f"- id: {qid}")
        at = next(i for i in range(start, len(out)) if out[i].startswith("  gold_text:"))
        out.insert(at + 1, f"  gold_chunks: [{', '.join(repr(i) for i in ids)}]".replace("'", '"'))
    if write:
        path.write_text("\n".join(out) + "\n")
        print(f"wrote gold_chunks for {len(resolved)} questions")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2], "--write" in sys.argv)
