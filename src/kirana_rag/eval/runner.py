"""Run the eval: retrieval metrics (no LLM), answer metrics at k, and an oracle-context pass."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import yaml

from .. import config, llm
from ..answer import Answer, answer_question
from ..ingest.chunk import Chunk
from ..ingest.pipeline import list_doc_ids, load_chunks
from ..retrieve import Index, load_index
from . import metrics
from .judge import judge

RESULTS_DIR = config.EVAL_DIR / "results"
MAX_K = max(metrics.KS)


def load_questions(path: Path, only: set[str] | None = None) -> list[dict]:
    qs = yaml.safe_load(path.read_text())
    return [q for q in qs if not only or q["id"] in only]


def _answer_record(ans: Answer, q: dict) -> dict:
    """Answer-side metrics for one answer (retrieved or oracle context)."""
    rec: dict = {
        "status": ans.status,
        "answer": ans.answer,
        "error": ans.error,
        "citations": [c.__dict__ for c in ans.citations],
        "tokens_in": ans.tokens_in,
        "tokens_out": ans.tokens_out,
        "llm_ms": ans.llm_ms,
    }
    rec["status_correct"] = ans.status == q["expected_status"]
    rec["facts_correct"] = metrics.facts_correct(ans.answer, q.get("must_contain", []))
    rec["citation_page_ok"] = metrics.citation_page_ok(
        [c.page for c in ans.citations], q.get("gold_pages", [])
    )
    rec["citations_verified"] = metrics.citations_verified_share(
        [c.verified for c in ans.citations]
    )
    if ans.error:
        rec["judge"], rec["judge_reason"] = "error", ans.error
    else:
        rec["judge"], rec["judge_reason"] = judge(q["question"], q["expected_answer"], ans.answer)
    # Disagreement between the deterministic check and the judge, listed for manual review.
    rec["disagree"] = rec["facts_correct"] is not None and rec["facts_correct"] != (
        rec["judge"] == "correct"
    )
    return rec


def _retrieval_record(index: Index, q: dict) -> tuple[dict, list]:
    hits = index.search(q["question"], MAX_K)
    pages = [h.chunk.pages for h in hits]
    gold = q.get("gold_pages", [])
    rank = metrics.rank_of_first_hit(pages, gold) if gold else None
    typed = [(h.chunk.pages, h.chunk.type) for h in hits]
    gold_chunks = q.get("gold_chunks", [])
    ids = [h.chunk.chunk_id for h in hits]
    crank = metrics.chunk_rank(ids, gold_chunks) if gold_chunks else None
    rec = {
        "first_gold_chunk_rank": crank,
        "chunk_hit": {str(k): metrics.hit_at(crank, k) for k in metrics.KS}
        if gold_chunks
        else None,
        "chunk_recall": (
            {str(k): metrics.chunk_recall_at(ids, gold_chunks, k) for k in metrics.KS}
            if gold_chunks
            else None
        ),
        "retrieved": [
            {
                "chunk_id": h.chunk.chunk_id,
                "pages": h.chunk.pages,
                "type": h.chunk.type,
                "score": round(h.score, 4),
            }
            for h in hits
        ],
        "first_gold_rank": rank,
        "mrr": metrics.reciprocal_rank(rank),
        "hit": {str(k): metrics.hit_at(rank, k) for k in metrics.KS},
        "gold_type_retrieved": {
            str(k): metrics.gold_chunk_type_retrieved(typed, gold, q["type"], k) for k in metrics.KS
        },
    }
    return rec, hits


def run_question(q: dict, index: Index, chunks: list[Chunk], k: int, oracle: bool) -> dict:
    rec: dict = {
        k_: q[k_]
        for k_ in ("id", "type", "question", "expected_answer", "gold_pages", "expected_status")
    }
    rec["must_contain"] = q.get("must_contain", [])
    rec["gold_chunks"] = q.get("gold_chunks", [])
    rec["retrieval"], hits = _retrieval_record(index, q)
    ans = answer_question(q["question"], [h.chunk for h in hits[:k]])
    rec["answer"] = _answer_record(ans, q)
    if oracle and q.get("gold_pages"):
        gold = set(q["gold_pages"])
        gold_chunks = [c for c in chunks if gold & set(c.pages)]
        rec["oracle"] = _answer_record(answer_question(q["question"], gold_chunks), q)
        rec["oracle_chunk_ids"] = [c.chunk_id for c in gold_chunks]
    return rec


def run_eval(
    questions: list[dict],
    doc_id: str | None,
    tag: str,
    k: int,
    oracle: bool = True,
    suite: str = "core",
    retriever: str = "hybrid",
) -> dict:
    """Run every question (2 in flight) and return the full results dict."""
    ids = [doc_id] if doc_id else list_doc_ids()
    if len(ids) > 1:
        raise ValueError(
            f"{len(ids)} documents are ingested; pass --doc <doc_id> so the eval is not polluted"
        )
    chunks = [c for d in ids for c in load_chunks(d)]
    index = load_index(ids[0], retriever)
    before = llm.Usage(**llm.USAGE.__dict__)
    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENCY) as pool:
        records = list(pool.map(lambda q: run_question(q, index, chunks, k, oracle), questions))
    s = config.settings()
    return {
        "tag": tag,
        "suite": suite,
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "k": k,
        "retriever": index.retriever,
        "oracle": oracle,
        "doc_ids": ids,
        "n_chunks": len(chunks),
        "models": {"text": s.model, "vision": s.vision_model},
        "tokens": {
            "in": llm.USAGE.tokens_in - before.tokens_in,
            "out": llm.USAGE.tokens_out - before.tokens_out,
            "note": "tokens of calls not served from the response cache in this process",
        },
        "records": records,
    }


def save(results: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{results['tag']}.json"
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    return path
