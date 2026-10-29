import json

from kirana_rag import answer, llm
from kirana_rag.answer import Citation, parse_json, verify_citation
from kirana_rag.ingest.chunk import Chunk
from kirana_rag.retrieve import Index

CHUNK = Chunk(
    "p4-t1",
    "d",
    [4],
    "table",
    "Financial review",
    "Table 1",
    [0, 0, 1, 1],
    "| Revenue | 6,910 | 7,655 | 8,420 |\n| Net debt (31 Dec) | 1,880 | 2,050 | 2,310 |",
    header="[Doc | p4 | table: Table 1]",
)
RETRIEVED = {"p4-t1": CHUNK}


def test_parse_json_plain_fenced_and_wrapped():
    assert parse_json('{"a": 1}') == {"a": 1}
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure! {"a": 1} hope that helps') == {"a": 1}
    assert parse_json("not json") is None
    assert parse_json("[1, 2]") is None


def test_verifier_accepts_verbatim_quote_ignoring_commas_and_case():
    c = verify_citation(Citation("p4-t1", 4, "net debt (31 dec) 1880"), RETRIEVED)
    assert c.verified


def test_verifier_rejects_altered_quote():
    c = verify_citation(Citation("p4-t1", 4, "Net debt (31 Dec) | 2,999"), RETRIEVED)
    assert not c.verified and "verbatim" in c.reason


def test_verifier_rejects_wrong_page():
    c = verify_citation(Citation("p4-t1", 5, "Revenue | 6,910"), RETRIEVED)
    assert not c.verified and "page" in c.reason


def test_verifier_rejects_unknown_chunk_id():
    c = verify_citation(Citation("p9-t9", 4, "Revenue"), RETRIEVED)
    assert not c.verified and "chunk_id" in c.reason


def _mock_llm(monkeypatch, replies: list[str]):
    calls = []

    def fake(prompt, system="", max_tokens=800, temperature=0.0, use_cache=True):
        calls.append(prompt)
        return llm.LLMResult(replies[min(len(calls) - 1, len(replies) - 1)], 10, 5)

    monkeypatch.setattr(llm, "complete", fake)
    return calls


def test_answer_question_with_mocked_llm(monkeypatch):
    reply = json.dumps(
        {
            "status": "answered",
            "answer": "Net debt was THB 2,310m.",
            "citations": [{"chunk_id": "p4-t1", "page": 4, "quote": "Net debt (31 Dec) | 1,880"}],
        }
    )
    _mock_llm(monkeypatch, [reply])
    ans = answer.answer_question("net debt?", [CHUNK])
    assert ans.status == "answered" and ans.citations[0].verified
    assert ans.tokens_in == 10 and ans.tokens_out == 5


def test_json_repair_retry_then_error(monkeypatch):
    good = '{"status": "refused", "answer": "not in report", "citations": []}'
    calls = _mock_llm(monkeypatch, ["garbage", good])
    ans = answer.answer_question("q", [CHUNK])
    assert ans.status == "refused" and len(calls) == 2

    calls = _mock_llm(monkeypatch, ["garbage", "still garbage"])
    ans = answer.answer_question("q", [CHUNK])
    assert ans.status == "error" and "JSON" in ans.error


def test_invalid_status_is_an_error_not_an_answer(monkeypatch):
    _mock_llm(monkeypatch, ['{"status": "maybe", "answer": "x", "citations": []}'])
    ans = answer.answer_question("q", [CHUNK])
    assert ans.status == "error"


def test_ask_retrieves_then_answers(monkeypatch):
    _mock_llm(monkeypatch, ['{"status": "refused", "answer": "no", "citations": []}'])
    ans = answer.ask("net debt 2310", Index([CHUNK]), k=3)
    assert ans.hits[0].chunk.chunk_id == "p4-t1" and ans.status == "refused"


def test_colliding_chunk_ids_are_qualified_by_doc():
    a = Chunk("p1-x1", "docA", [1], "text", "", "", [0, 0, 1, 1], "alpha")
    b = Chunk("p1-x1", "docB", [1], "text", "", "", [0, 0, 1, 1], "beta")
    assert set(answer.chunk_refs([a, b])) == {"docA/p1-x1", "docB/p1-x1"}
    assert set(answer.chunk_refs([a])) == {"p1-x1"}
