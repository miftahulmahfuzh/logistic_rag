"""Retrieval-only metrics (no LLM) over the eval sets: first-gold-chunk rank, hit@1, recall@5.

Usage: uv run python scripts/retrieval_ablation.py [--retriever bm25,hybrid] [--normalise none,spelling,full] [--rule] [--detail]
Needs the Kirana report and both holdout reports ingested (see scripts/make_holdout_pdf.py and make_holdout2_pdf.py).
`--rule` prints the pre-registered decision rule of eval/ITERATIONS.md (holdout v2 section); `--detail` lists the first-gold
rank of every question on the holdout sets for every setting.
"""

import argparse
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kirana_rag import config
from kirana_rag.eval import metrics, runner
from kirana_rag.ingest.pipeline import list_doc_ids
from kirana_rag.retrieve import Index, load_index

SETS = {
    "core": ("questions.yaml", "kirana"),
    "hard": ("questions_hard.yaml", "kirana"),
    "holdout": ("questions_holdout.yaml", "northmere"),
    "holdout2": ("questions_holdout2.yaml", "halbrook"),
}


def evaluate(index: Index, questions: list[dict]) -> dict:
    """Per-question first-gold-chunk rank over the full ranking, so a gold chunk is always ranked."""
    ranks, recall5 = {}, []
    for q in questions:
        gold = q.get("gold_chunks")
        if not gold:
            continue
        ids = [h.chunk.chunk_id for h in index.search(q["question"], len(index.chunks))]
        ranks[q["id"]] = metrics.chunk_rank(ids, gold)
        recall5.append(metrics.chunk_recall_at(ids, gold, 5))
    return {"ranks": ranks, "recall5": recall5}


def summary(ranks: list[int], recall5: list[float]) -> dict[str, float]:
    return {
        "n": len(ranks),
        "mean_rank": statistics.mean(ranks),
        "hit@1": statistics.mean(r == 1 for r in ranks),
        "recall@5": statistics.mean(recall5),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--retriever", default="hybrid")
    ap.add_argument("--normalise", default="full")
    ap.add_argument("--rule", action="store_true")
    ap.add_argument("--detail", action="store_true")
    args = ap.parse_args()
    docs = {
        name: next(d for d in list_doc_ids() if d.startswith(name))
        for name in ("kirana", "northmere", "halbrook")
    }
    results: dict[tuple[str, str, str], dict] = {}  # (retriever, mode, set) -> evaluate()
    for retriever in args.retriever.split(","):
        for mode in args.normalise.split(","):
            os.environ["KIRANA_NORMALISE"] = mode
            for name, (qfile, prefix) in SETS.items():
                index = load_index(docs[prefix], retriever)
                if retriever == "hybrid" and not index.hybrid:
                    sys.exit("dense model unavailable: refusing to report BM25 numbers as hybrid")
                qs = runner.load_questions(config.EVAL_DIR / qfile)
                results[retriever, mode, name] = evaluate(index, qs)

    def kirana(retriever: str, mode: str) -> tuple[list[int], list[float]]:
        a, b = (results[retriever, mode, s] for s in ("core", "hard"))
        return [*a["ranks"].values(), *b["ranks"].values()], a["recall5"] + b["recall5"]

    print(
        "| retriever | normalise | set | n | mean first-gold rank | hit@1 | recall@5 |\n"
        "|---|---|---|---|---|---|---|"
    )
    pooled: dict[tuple[str, str, str], float] = {}
    for retriever in args.retriever.split(","):
        for mode in args.normalise.split(","):
            rows = {s: results[retriever, mode, s] for s in SETS}
            rows_kirana = kirana(retriever, mode)
            sets = [*SETS, "Kirana (core+hard)"]
            for name in sets:
                r = (
                    summary(*rows_kirana)
                    if name.startswith("Kirana")
                    else summary(list(rows[name]["ranks"].values()), rows[name]["recall5"])
                )
                pooled[retriever, mode, name.split()[0]] = round(r["mean_rank"], 2)
                print(
                    f"| {retriever} | {mode} | {name} | {r['n']} | {r['mean_rank']:.2f} | "
                    f"{r['hit@1']:.0%} | {r['recall@5']:.0%} |"
                )
    if args.detail:
        print("\nFirst-gold rank per question (holdout sets):")
        for s in ("holdout", "holdout2"):
            ids = (
                list(next(iter(results.values()))["ranks"])
                if False
                else sorted({i for (r, m, n), v in results.items() if n == s for i in v["ranks"]})
            )
            print(f"\n{s}: " + " ".join(ids))
            for (retriever, mode, n), v in results.items():
                if n == s:
                    print(
                        f"{retriever:7} {mode:9} "
                        + " ".join(f"{v['ranks'].get(i, '-')!s:>3}" for i in ids)
                    )
    if args.rule:
        print_rule(pooled)


def print_rule(pooled: dict[tuple[str, str, str], float]) -> None:
    """Apply the rule fixed in eval/ITERATIONS.md: candidate <= reference (2 decimals) on all three sets."""
    checks = [
        (
            "Snowball: hybrid full vs hybrid spelling (primary)",
            ("hybrid", "full"),
            ("hybrid", "spelling"),
        ),
        (
            "Snowball: bm25 full vs bm25 spelling (secondary)",
            ("bm25", "full"),
            ("bm25", "spelling"),
        ),
        (
            "Spelling pass: hybrid spelling vs hybrid none",
            ("hybrid", "spelling"),
            ("hybrid", "none"),
        ),
        ("Spelling pass: bm25 spelling vs bm25 none", ("bm25", "spelling"), ("bm25", "none")),
        ("Retriever: hybrid vs bm25, spelling", ("hybrid", "spelling"), ("bm25", "spelling")),
        ("Retriever: hybrid vs bm25, none", ("hybrid", "none"), ("bm25", "none")),
        ("Retriever: hybrid vs bm25, full", ("hybrid", "full"), ("bm25", "full")),
    ]
    sets = ("Kirana", "holdout", "holdout2")
    print(
        "\n| comparison (candidate vs reference) | "
        + " | ".join(sets)
        + " | verdict |\n|---|---|---|---|---|---|"
    )
    for label, cand, ref in checks:
        try:
            pairs = [(pooled[(*cand, s)], pooled[(*ref, s)]) for s in sets]
        except KeyError:
            continue
        ok = all(c <= r for c, r in pairs)
        gain = any(c < r for c, r in pairs)
        verdict = ("passes, gain somewhere" if gain else "passes, no gain") if ok else "FAILS"
        cells = " | ".join(f"{c:.2f} vs {r:.2f}" for c, r in pairs)
        print(f"| {label} | {cells} | {verdict} |")


if __name__ == "__main__":
    main()
