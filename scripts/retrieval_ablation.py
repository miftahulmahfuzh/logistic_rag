"""Retrieval-only metrics (no LLM) over the eval sets: first-gold-chunk rank, hit@1, recall@5.

Usage: uv run python scripts/retrieval_ablation.py [--retriever bm25|hybrid] [--normalise none,spelling,full]
Needs the Kirana report and the holdout report ingested (see scripts/make_holdout_pdf.py).
"""

import argparse
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kirana_rag import config  # noqa: E402
from kirana_rag.eval import metrics, runner  # noqa: E402
from kirana_rag.ingest.pipeline import list_doc_ids  # noqa: E402
from kirana_rag.retrieve import Index, load_index  # noqa: E402

SETS = {
    "core": ("questions.yaml", "kirana"),
    "hard": ("questions_hard.yaml", "kirana"),
    "holdout": ("questions_holdout.yaml", "northmere"),
}


def evaluate(index: Index, questions: list[dict], **search_args) -> dict[str, float]:
    ranks, hit1, recall5 = [], [], []
    for q in questions:
        gold = q.get("gold_chunks")
        if not gold:
            continue
        ids = [
            h.chunk.chunk_id for h in index.search(q["question"], len(index.chunks), **search_args)
        ]
        rank = metrics.chunk_rank(ids, gold)
        ranks.append(rank)
        hit1.append(rank == 1)
        recall5.append(metrics.chunk_recall_at(ids, gold, 5))
    return {
        "n": len(ranks),
        "mean_rank": statistics.mean(ranks),
        "hit@1": statistics.mean(hit1),
        "recall@5": statistics.mean(recall5),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--retriever", default=None)
    ap.add_argument("--normalise", default="full")
    args = ap.parse_args()
    docs = {
        name: next(d for d in list_doc_ids() if d.startswith(name))
        for name in ("kirana", "northmere")
    }
    extra = {"retriever": args.retriever} if args.retriever else {}
    print(
        "| normalise | set | n | mean first-gold rank | hit@1 | recall@5 |\n|---|---|---|---|---|---|"
    )
    for mode in args.normalise.split(","):
        os.environ["KIRANA_NORMALISE"] = mode
        for name, (qfile, prefix) in SETS.items():
            index = load_index(docs[prefix])
            r = evaluate(index, runner.load_questions(config.EVAL_DIR / qfile), **extra)
            print(
                f"| {mode} | {name} | {r['n']} | {r['mean_rank']:.2f} | {r['hit@1']:.0%} | {r['recall@5']:.0%} |"
            )


if __name__ == "__main__":
    main()
