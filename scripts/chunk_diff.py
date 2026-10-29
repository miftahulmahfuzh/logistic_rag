"""Compare two chunks.jsonl files by chunk text: prints chunks removed, added and (same id) changed.

Chunks are matched by their text (whitespace-normalised), so a renumbered chunk with the same text is not a
difference. Used as the regression check for ingestion changes: pages that are not special must not differ.

Usage: uv run python scripts/chunk_diff.py <before.jsonl> <after.jsonl> [--full]
"""

import json
import sys
from pathlib import Path


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def norm(text: str) -> str:
    return " ".join(text.split())


def describe(c: dict, full: bool) -> str:
    pages = c["pages"]
    span = f"p{pages[0]}" if len(pages) == 1 else f"p{pages[0]}-{pages[-1]}"
    text = norm(c["text"])
    return f"{c['chunk_id']} {span} {c['type']} [{c['section']}] {text if full else text[:110]!r}"


def diff(before: list[dict], after: list[dict]) -> tuple[list[dict], list[dict]]:
    """(removed, added): chunks of `before` whose text is not in `after`, and the reverse."""
    after_texts = {norm(c["text"]) for c in after}
    before_texts = {norm(c["text"]) for c in before}
    removed = [c for c in before if norm(c["text"]) not in after_texts]
    added = [c for c in after if norm(c["text"]) not in before_texts]
    return removed, added


def main(before: Path, after: Path, full: bool) -> None:
    b, a = load(before), load(after)
    removed, added = diff(b, a)
    moved = [
        (x["chunk_id"], y["chunk_id"])
        for x in b
        for y in a
        if norm(x["text"]) == norm(y["text"]) and x["chunk_id"] != y["chunk_id"]
    ]
    print(f"before {len(b)} chunks, after {len(a)} chunks")
    print(f"identical text: {len(b) - len(removed)}; renumbered only: {len(moved)}")
    print(f"removed ({len(removed)}):")
    for c in removed:
        print("  -", describe(c, full))
    print(f"added ({len(added)}):")
    for c in added:
        print("  +", describe(c, full))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--full"]
    if len(args) != 2:
        sys.exit(__doc__)
    main(Path(args[0]), Path(args[1]), "--full" in sys.argv)
