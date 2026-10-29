import pytest

from kirana_rag.eval import metrics, report


def test_rank_and_hit_at():
    pages = [[3], [9], [7, 8], [2]]
    assert metrics.rank_of_first_hit(pages, [8]) == 3
    assert metrics.rank_of_first_hit(pages, [1]) is None
    assert metrics.hit_at(3, 3) and not metrics.hit_at(3, 1) and not metrics.hit_at(None, 8)
    assert metrics.reciprocal_rank(4) == 0.25 and metrics.reciprocal_rank(None) == 0.0


def test_gold_chunk_type_retrieved():
    retrieved = [([5], "text"), ([5], "figure"), ([4], "table")]
    assert metrics.gold_chunk_type_retrieved(retrieved, [5], "chart", 5) is True
    assert metrics.gold_chunk_type_retrieved(retrieved, [5], "chart", 1) is False
    assert metrics.gold_chunk_type_retrieved(retrieved, [4], "table", 3) is True
    assert metrics.gold_chunk_type_retrieved(retrieved, [5], "prose", 3) is None


def test_facts_correct_all_of_and_any_of():
    assert metrics.facts_correct("Net debt is THB 2,310m", ["2310"]) is True
    assert metrics.facts_correct("It was 82", ["82", "96"]) is False
    assert metrics.facts_correct("about 1.9", ["2.40", ["1.90", "1.9"]]) is False
    assert metrics.facts_correct("2.40 and about 1.9", ["2.40", ["1.90", "1.9"]]) is True
    assert metrics.facts_correct("anything", []) is None


def test_citation_page_ok():
    assert metrics.citation_page_ok([4, 9], [9]) is True
    assert metrics.citation_page_ok([4], [9]) is False
    assert metrics.citation_page_ok([4], []) is None


def test_citations_verified_share():
    assert metrics.citations_verified_share([True, False, True, True]) == 0.75
    assert metrics.citations_verified_share([]) is None


def test_refusal_stats():
    recs = [
        ("refused", "refused"),
        ("refused", "answered"),
        ("answered", "refused"),
        ("answered", "answered"),
        ("conflict", "conflict"),
    ]
    s = metrics.refusal_stats(recs)
    assert s["refusal_recall"] == 0.5
    assert s["refusal_precision"] == 0.5
    assert s["false_refusal_rate"] == pytest.approx(1 / 3)


def test_percentile_and_latency_summary():
    vals = [10, 20, 30, 40, 50]
    assert metrics.percentile(vals, 50) == 30
    assert metrics.percentile(vals, 95) == 50
    assert metrics.percentile([], 50) is None
    assert metrics.latency_summary(vals)["mean"] == 30


def _record(qid: str, status: str, expected: str, rank: int | None, judge: str) -> dict:
    ans = {
        "status": status,
        "answer": "a",
        "error": "",
        "citations": [],
        "tokens_in": 10,
        "tokens_out": 5,
        "llm_ms": 100.0,
        "status_correct": status == expected,
        "facts_correct": True,
        "citation_page_ok": True,
        "citations_verified": 1.0,
        "judge": judge,
        "judge_reason": "",
        "disagree": False,
    }
    hit = {str(k): metrics.hit_at(rank, k) for k in metrics.KS}
    return {
        "id": qid,
        "type": "table",
        "gold_pages": [4],
        "expected_status": expected,
        "retrieval": {
            "hit": hit,
            "mrr": metrics.reciprocal_rank(rank),
            "gold_type_retrieved": {str(k): True for k in metrics.KS},
            "first_gold_rank": rank,
            "retrieved": [{"chunk_id": "p4-t1", "score": 1.0}],
        },
        "answer": ans,
        "oracle": dict(ans),
    }


def test_summarise_hand_made_results():
    results = {
        "models": {"text": "glm-5.3", "vision": "glm-4.6v"},
        "records": [
            _record("a", "answered", "answered", 1, "correct"),
            _record("b", "answered", "answered", 4, "wrong"),
            _record("c", "refused", "refused", None, "correct"),
        ],
    }
    s = report.summarise(results)
    assert s["n"] == 3 and s["n_answerable"] == 2
    assert s["hit@1"] == 0.5 and s["hit@3"] == 0.5 and s["hit@5"] == 1.0
    assert s["mrr"] == pytest.approx((1 + 0.25) / 2)
    assert s["answer"]["judge_correct"] == pytest.approx(2 / 3)
    assert s["refusal"]["refusal_recall"] == 1.0


def _repeat_run(judges: list[str]) -> dict:
    return {
        "n_chunks": 3,
        "retriever": "hybrid",
        "k": 8,
        "models": {"text": "glm-5.3", "vision": "glm-4.6v"},
        "records": [_record(f"q{i}", "answered", "answered", 1, j) for i, j in enumerate(judges)],
    }


def test_summarise_repeats_mean_and_range():
    runs = [
        _repeat_run(["correct", "correct", "wrong", "correct"]),
        _repeat_run(["correct", "correct", "correct", "correct"]),
        _repeat_run(["correct", "wrong", "wrong", "correct"]),
    ]
    out = report.summarise_repeats(runs)
    mean, lo, hi = out["judge correct"]
    assert (lo, hi) == (0.5, 1.0) and mean == pytest.approx(0.75)
    assert report.question_judges(runs)["q1"] == ["correct", "correct", "wrong"]
    assert "q2: wrong, correct, wrong" in report.render_repeats("t", runs)
