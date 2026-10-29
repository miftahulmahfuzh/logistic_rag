"""Summaries from per-question records, and the RESULTS.md renderer."""

import json
import re
from pathlib import Path

from .. import config
from . import metrics

ANALYSIS_FILE = "failure_analysis.md"
REPEAT_TAG_RE = re.compile(r"_r\d+$")  # `<tag>_r1`: one repeat of a repeated run


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{100 * v:.0f}%"


def summarise(results: dict) -> dict:
    """All headline numbers for one run, computed from the raw records."""
    recs = results["records"]
    answerable = [r for r in recs if r["expected_status"] != "refused"]
    out: dict = {"n": len(recs), "n_answerable": len(answerable)}
    recall_recs = [r for r in answerable if r["gold_pages"]]
    for k in metrics.KS:
        out[f"hit@{k}"] = metrics.mean_or_none([r["retrieval"]["hit"][str(k)] for r in recall_recs])
    out["mrr"] = metrics.mean_or_none([r["retrieval"]["mrr"] for r in recall_recs])
    typed = [r for r in recall_recs if r["retrieval"]["gold_type_retrieved"]["5"] is not None]
    out["gold_type@5"] = metrics.mean_or_none(
        [r["retrieval"]["gold_type_retrieved"]["5"] for r in typed]
    )
    for side in ("answer", "oracle"):
        rs = [r[side] for r in recs if side in r]
        out[side] = {
            "n": len(rs),
            "status_correct": metrics.mean_or_none([x["status_correct"] for x in rs]),
            "facts_correct": metrics.mean_or_none([x["facts_correct"] for x in rs]),
            "judge_correct": metrics.mean_or_none([x["judge"] == "correct" for x in rs]),
            "judge_partial": metrics.mean_or_none([x["judge"] == "partial" for x in rs]),
            "citation_page_ok": metrics.mean_or_none([x["citation_page_ok"] for x in rs]),
            "citations_verified": metrics.mean_or_none([x["citations_verified"] for x in rs]),
            "errors": sum(1 for x in rs if x["error"]),
        }
    out["refusal"] = metrics.refusal_stats(
        [(r["expected_status"], r["answer"]["status"]) for r in recs]
    )
    lat = [r["answer"]["llm_ms"] for r in recs]
    out["llm_latency_ms"] = metrics.latency_summary(lat)
    out["tokens"] = {
        "in": sum(r["answer"]["tokens_in"] for r in recs),
        "out": sum(r["answer"]["tokens_out"] for r in recs),
    }
    chunk_recs = [r for r in recs if r["retrieval"].get("chunk_hit")]
    for k in metrics.KS:
        out[f"chunk_hit@{k}"] = metrics.mean_or_none(
            [r["retrieval"]["chunk_hit"][str(k)] for r in chunk_recs]
        )
    out["chunk_recall@5"] = metrics.mean_or_none(
        [r["retrieval"]["chunk_recall"]["5"] for r in chunk_recs]
    )
    model = results["models"]["text"]
    costs = [
        config.estimate_cost(model, r["answer"]["tokens_in"], r["answer"]["tokens_out"])
        for r in recs
    ]
    out["cost_usd"] = None if None in costs else sum(costs)
    out["by_type"] = _by_type(recs)
    out["unanswerable"] = [
        {
            "id": r["id"],
            "status": r["answer"]["status"],
            "top": [(h["chunk_id"], h["score"]) for h in r["retrieval"]["retrieved"][:3]],
        }
        for r in recs
        if r["expected_status"] == "refused"
    ]
    return out


def _by_type(recs: list[dict]) -> dict[str, dict]:
    types = sorted({r["type"] for r in recs})
    rows = {}
    for t in types:
        rs = [r for r in recs if r["type"] == t]
        gold = [r for r in rs if r["gold_pages"] and r["expected_status"] != "refused"]
        rows[t] = {
            "n": len(rs),
            "hit@1": metrics.mean_or_none([r["retrieval"]["hit"]["1"] for r in gold]),
            "hit@5": metrics.mean_or_none([r["retrieval"]["hit"]["5"] for r in gold]),
            "mrr": metrics.mean_or_none([r["retrieval"]["mrr"] for r in gold]),
            "status": metrics.mean_or_none([r["answer"]["status_correct"] for r in rs]),
            "facts": metrics.mean_or_none([r["answer"]["facts_correct"] for r in rs]),
            "judge": metrics.mean_or_none([r["answer"]["judge"] == "correct" for r in rs]),
            "oracle_judge": metrics.mean_or_none(
                [r["oracle"]["judge"] == "correct" for r in rs if "oracle" in r]
            ),
        }
    return rows


def _row(label: str, a: str, b: str | None = None) -> str:
    return f"| {label} | {a} |" + (f" {b} |" if b is not None else "")


def render(results_dir: Path, analysis_path: Path, suite: str = "core") -> str:
    """RESULTS.md: baseline vs latest side by side, per-type, per-question, failures, analysis."""
    loaded = {p.stem: json.loads(p.read_text()) for p in sorted(results_dir.glob("*.json"))}
    runs = {
        t: r
        for t, r in loaded.items()
        if r.get("suite", "core") == suite and not REPEAT_TAG_RE.search(t)
    }
    if not runs:
        return "# Results\n\nNo runs yet.\n"
    base = next((r for t, r in runs.items() if t.endswith("baseline")), next(iter(runs.values())))
    # `<tag>_k3` tags are k-sweep runs, `<tag>_bm25` are retriever-separation runs
    main_runs = [t for t in runs if "_k" not in t and not t.endswith("_bm25")] or list(runs)
    latest_tag = max(main_runs, key=lambda t: runs[t].get("finished_at", ""))
    latest = runs[latest_tag]
    sb, sl = summarise(base), summarise(latest)
    two = base is not latest
    lines = [
        f"# Evaluation results ({suite} set)",
        "",
        "*Regenerated by `kirana eval`. Do not edit by hand; the failure analysis "
        f"lives in `eval/{analysis_path.name}` and is included below.*",
        "",
    ]
    lines += [
        f"Runs on disk: {', '.join(f'`{t}` (k={r["k"]})' for t, r in runs.items())}. "
        f"Corpus: {base['n_chunks']} chunks. Text model `{base['models']['text']}`, "
        f"vision model `{base['models']['vision']}`.",
        "",
    ]
    head = "| metric | baseline |" + (f" {latest_tag} |" if two else "")
    lines += ["## Summary", "", head, "|---|---|" + ("---|" if two else "")]

    def add(label: str, getter) -> None:
        lines.append(_row(label, getter(sb), getter(sl) if two else None))

    add("**Retrieval (no LLM)**, answerable questions with gold pages", lambda s: "")
    for k in metrics.KS:
        add(f"hit@{k}", lambda s, k=k: _pct(s[f"hit@{k}"]))
    add("MRR", lambda s: "n/a" if s["mrr"] is None else f"{s['mrr']:.3f}")
    for k in metrics.KS:
        add(
            f"chunk-level hit@{k} (gold chunk ids)",
            lambda s, k=k: _pct(s[f"chunk_hit@{k}"]),
        )
    add("chunk-level recall@5 (share of gold chunks in top 5)", lambda s: _pct(s["chunk_recall@5"]))
    add("gold chunk type in top 5 (table/figure questions)", lambda s: _pct(s["gold_type@5"]))
    for side, title in (
        ("answer", "Answer, retrieved context"),
        ("oracle", "Answer, oracle (gold-page) context"),
    ):
        add(f"**{title}**", lambda s: "")
        for key, label in (
            ("status_correct", "status correct"),
            ("facts_correct", "facts correct (must_contain)"),
            ("judge_correct", "judge: correct"),
            ("judge_partial", "judge: partial"),
            ("citation_page_ok", "a cited page is a gold page"),
            ("citations_verified", "citations verified by code"),
            ("errors", "parse/format errors"),
        ):
            fmt = (
                (lambda s, side=side, key=key: str(s[side][key]))
                if key == "errors"
                else (lambda s, side=side, key=key: _pct(s[side][key]))
            )
            add(label, fmt)
    add("**Refusal behaviour**", lambda s: "")
    add("refusal recall (unanswerable set)", lambda s: _pct(s["refusal"]["refusal_recall"]))
    add("refusal precision", lambda s: _pct(s["refusal"]["refusal_precision"]))
    add("false-refusal rate (answerable set)", lambda s: _pct(s["refusal"]["false_refusal_rate"]))
    add("**Cost / latency (answer call)**", lambda s: "")
    add(
        "LLM latency mean / p50 / p95 (ms)",
        lambda s: " / ".join(
            "n/a" if v is None else f"{v:.0f}" for v in s["llm_latency_ms"].values()
        ),
    )
    add("est. cost of the answer calls at z.ai list price (USD)", lambda s: _usd(s["cost_usd"]))
    add(
        "tokens in / out (answer calls, whole set)",
        lambda s: f"{s['tokens']['in']} / {s['tokens']['out']}",
    )
    lines += [
        "",
        "Latency note: cached replies report the original call's latency. Cost uses z.ai pay-as-you-go list "
        "prices (the author pays a flat subscription); it covers the answer calls only, not judge, oracle or "
        "ingestion calls.",
        "",
    ]

    lines += [
        "## By question type (latest run)",
        "",
        "| type | n | hit@1 | hit@5 | MRR | status | facts | judge | judge (oracle) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for t, r in sl["by_type"].items():
        mrr = "n/a" if r["mrr"] is None else f"{r['mrr']:.2f}"
        lines.append(
            f"| {t} | {r['n']} | {_pct(r['hit@1'])} | {_pct(r['hit@5'])} | {mrr} | {_pct(r['status'])} | "
            f"{_pct(r['facts'])} | {_pct(r['judge'])} | {_pct(r['oracle_judge'])} |"
        )

    lines += [
        "",
        "## Unanswerable questions (excluded from recall)",
        "",
        "| id | status | top retrieved (chunk, score) |",
        "|---|---|---|",
    ]
    for u in sl["unanswerable"]:
        lines.append(
            f"| {u['id']} | {u['status']} | {', '.join(f'{c} {s}' for c, s in u['top'])} |"
        )

    lines += [
        "",
        f"## Per question (`{latest_tag}`)",
        "",
        "| id | type | gold page rank | gold chunk rank | status | facts | judge | oracle judge | cites ok | verified | note |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    failures = []
    for r in latest["records"]:
        a, o = r["answer"], r.get("oracle")
        flag = "disagree" if a["disagree"] else ""
        lines.append(
            f"| {r['id']} | {r['type']} | {r['retrieval']['first_gold_rank'] or '-'} | "
            f"{r['retrieval'].get('first_gold_chunk_rank') or '-'} | "
            f"{a['status']}{'' if a['status_correct'] else ' (WRONG, want ' + r['expected_status'] + ')'} | "
            f"{_tick(a['facts_correct'])} | {a['judge']} | {o['judge'] if o else '-'} | {_tick(a['citation_page_ok'])} | "
            f"{_pct(a['citations_verified'])} | {flag} |"
        )
        if (
            not a["status_correct"]
            or a["facts_correct"] is False
            or a["judge"] != "correct"
            or a["disagree"]
            or (r["retrieval"]["first_gold_rank"] or 0) > 5
            or (
                r["gold_pages"]
                and r["expected_status"] != "refused"
                and r["retrieval"]["first_gold_rank"] is None
            )
        ):
            failures.append(r)

    lines += ["", f"## Failure list (`{latest_tag}`, generated; every non-perfect question)", ""]
    for r in failures:
        a, o = r["answer"], r.get("oracle")
        lines += [
            f"### {r['id']} ({r['type']}): {r['question']}",
            "",
            f"- expected ({r['expected_status']}): {r['expected_answer']}",
            f"- got ({a['status']}): {a['answer']}",
            f"- judge: {a['judge']}: {a['judge_reason']}",
            f"- retrieval: gold pages {r['gold_pages']}, first gold rank {r['retrieval']['first_gold_rank']}, "
            f"top 5: {', '.join(h['chunk_id'] for h in r['retrieval']['retrieved'][:5])}",
            f"- unverified citations: {sum(1 for c in a['citations'] if not c['verified'])} of {len(a['citations'])}",
        ]
        if o:
            lines.append(
                f"- oracle context ({', '.join(r['oracle_chunk_ids'])}): {o['status']}, judge {o['judge']}: {o['answer']}"
            )
        lines.append("")
    if not failures:
        lines += ["No failures. The test set is probably too easy; add harder questions.", ""]

    ks = sorted((r["k"], t) for t, r in runs.items())
    if len(ks) > 1:
        lines += [
            "## k sweep (same questions, same chunks)",
            "",
            "| run | k | status correct | facts correct | judge correct | cites ok | refusal recall | false refusals |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for k, t in ks:
            s = summarise(runs[t])
            lines.append(
                f"| {t} | {k} | {_pct(s['answer']['status_correct'])} | {_pct(s['answer']['facts_correct'])} | "
                f"{_pct(s['answer']['judge_correct'])} | {_pct(s['answer']['citation_page_ok'])} | "
                f"{_pct(s['refusal']['refusal_recall'])} | {_pct(s['refusal']['false_refusal_rate'])} |"
            )
        lines.append("")

    if analysis_path.exists():
        lines += ["", analysis_path.read_text().rstrip(), ""]
    else:
        lines += ["", "## Failure analysis", "", "_Not written yet (Phase 5, by hand)._", ""]
    return "\n".join(lines)


def _usd(v: float | None) -> str:
    return "unknown" if v is None else f"${v:.4f}"


def _tick(v: bool | None) -> str:
    return "-" if v is None else ("yes" if v else "NO")


REPEAT_METRICS = {
    "judge correct": lambda s: s["answer"]["judge_correct"],
    "facts correct": lambda s: s["answer"]["facts_correct"],
    "status correct": lambda s: s["answer"]["status_correct"],
    "false refusal rate": lambda s: s["refusal"]["false_refusal_rate"],
    "chunk hit@8": lambda s: s["chunk_hit@8"],
    "page hit@8": lambda s: s["hit@8"],
}


def load_repeats(results_dir: Path, tag: str) -> list[dict]:
    """Results of `<tag>_r1`, `<tag>_r2`, ... in repeat order."""
    paths = [
        p
        for p in results_dir.glob(f"{tag}_r*.json")
        if re.fullmatch(r"r\d+", p.stem[len(tag) + 1 :])
    ]
    paths.sort(key=lambda p: int(p.stem.rsplit("_r", 1)[1]))
    return [json.loads(p.read_text()) for p in paths]


def summarise_repeats(runs: list[dict]) -> dict[str, tuple[float, float, float] | None]:
    """Mean, min and max of each headline metric over the repeats (None if a metric is undefined)."""
    sums = [summarise(r) for r in runs]
    out: dict[str, tuple[float, float, float] | None] = {}
    for name, getter in REPEAT_METRICS.items():
        vals = [v for s in sums if (v := getter(s)) is not None]
        out[name] = (sum(vals) / len(vals), min(vals), max(vals)) if vals else None
    return out


def question_judges(runs: list[dict]) -> dict[str, list[str]]:
    """Judge verdict of every question in every repeat, in repeat order."""
    out: dict[str, list[str]] = {}
    for r in runs:
        for rec in r["records"]:
            out.setdefault(rec["id"], []).append(rec["answer"]["judge"])
    return out


def render_repeats(tag: str, runs: list[dict]) -> str:
    n = len(runs)
    lines = [
        f"{tag}: {n} repeats, corpus {runs[0]['n_chunks']} chunks, retriever {runs[0]['retriever']}, k={runs[0]['k']}"
    ]
    lines += ["", "| metric | mean | min | max |", "|---|---|---|---|"]
    for name, v in summarise_repeats(runs).items():
        lines.append(
            f"| {name} | n/a | | |"
            if v is None
            else f"| {name} | {_pct(v[0])} | {_pct(v[1])} | {_pct(v[2])} |"
        )
    unstable = {q: j for q, j in question_judges(runs).items() if len(set(j)) > 1}
    if unstable:
        lines += ["", "Questions whose verdict differs between repeats:"]
        lines += [f"- {q}: {', '.join(j)}" for q, j in sorted(unstable.items())]
    return "\n".join(lines)
