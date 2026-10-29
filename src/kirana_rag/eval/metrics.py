"""Pure metric functions for the eval: no I/O, no LLM. Unit-tested on hand-made inputs."""

import re
import statistics
from collections.abc import Sequence

KS = (1, 3, 5, 8)

# Chunk types that should carry the facts for each question type (None: no expectation).
EXPECTED_CHUNK_TYPES: dict[str, set[str] | None] = {
    "table": {"table"},
    "table_crossref": {"table"},
    "chart": {"figure", "scan"},
    "kpi": {"figure", "scan"},
    "diagram": {"figure", "scan"},
    "scan": {"scan", "figure"},
}


def normalise(text: str) -> str:
    """Lowercase, remove thousands commas and markdown noise, collapse whitespace."""
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text.lower())
    text = re.sub(r"[*`|_]", " ", text)
    return " ".join(text.split())


def rank_of_first_hit(
    retrieved_pages: Sequence[Sequence[int]], gold_pages: Sequence[int]
) -> int | None:
    """1-based rank of the first retrieved chunk whose pages intersect gold_pages."""
    gold = set(gold_pages)
    for rank, pages in enumerate(retrieved_pages, 1):
        if gold & set(pages):
            return rank
    return None


def hit_at(rank: int | None, k: int) -> bool:
    return rank is not None and rank <= k


def reciprocal_rank(rank: int | None) -> float:
    return 0.0 if rank is None else 1.0 / rank


def gold_chunk_type_retrieved(
    retrieved: Sequence[tuple[Sequence[int], str]], gold_pages: Sequence[int], q_type: str, k: int
) -> bool | None:
    """Did a chunk of the expected type covering a gold page appear in the top k? None if n/a."""
    want = EXPECTED_CHUNK_TYPES.get(q_type)
    if want is None:
        return None
    gold = set(gold_pages)
    return any(t in want and gold & set(p) for p, t in retrieved[:k])


def facts_correct(answer: str, must_contain: Sequence) -> bool | None:
    """Every entry must appear; an entry that is a list is satisfied by any of its strings."""
    if not must_contain:
        return None
    text = normalise(answer)
    for entry in must_contain:
        options = entry if isinstance(entry, list) else [entry]
        if not any(normalise(str(o)) in text for o in options):
            return False
    return True


def citation_page_ok(cited_pages: Sequence[int | None], gold_pages: Sequence[int]) -> bool | None:
    if not gold_pages:
        return None
    return any(p in set(gold_pages) for p in cited_pages)


def citations_verified_share(flags: Sequence[bool]) -> float | None:
    return None if not flags else sum(flags) / len(flags)


def refusal_stats(records: Sequence[tuple[str, str]]) -> dict[str, float | None]:
    """records: (expected_status, predicted_status). Refusal precision/recall and false-refusal rate."""
    unanswerable = [(e, p) for e, p in records if e == "refused"]
    answerable = [(e, p) for e, p in records if e != "refused"]
    predicted_refused = [(e, p) for e, p in records if p == "refused"]
    tp = sum(1 for e, p in unanswerable if p == "refused")
    return {
        "refusal_recall": tp / len(unanswerable) if unanswerable else None,
        "refusal_precision": tp / len(predicted_refused) if predicted_refused else None,
        "false_refusal_rate": (
            sum(1 for _, p in answerable if p == "refused") / len(answerable)
            if answerable
            else None
        ),
    }


def percentile(values: Sequence[float], pct: float) -> float | None:
    """Nearest-rank percentile; None on empty input."""
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, round(pct / 100 * len(ordered) + 0.5) - 1))
    return ordered[idx]


def latency_summary(values: Sequence[float]) -> dict[str, float | None]:
    return {
        "mean": statistics.fmean(values) if values else None,
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
    }


def mean_or_none(values: Sequence[float | bool | None]) -> float | None:
    vals = [float(v) for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None
