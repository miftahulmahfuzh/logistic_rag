"""LLM judge: correct | partial | wrong. Never sees the retrieved context."""

from .. import llm, prompts
from ..answer import parse_json

VERDICTS = {"correct", "partial", "wrong"}


def judge(question: str, expected: str, answer: str) -> tuple[str, str]:
    """Returns (verdict, one-sentence reason). Verdict is 'error' if the judge reply is unusable."""
    prompt = prompts.JUDGE_USER.format(question=question, expected=expected, answer=answer)
    res = llm.complete(prompt, system=prompts.JUDGE_SYSTEM, max_tokens=300)
    obj = parse_json(res.text)
    verdict = str((obj or {}).get("verdict", "")).lower()
    if verdict not in VERDICTS:
        return "error", f"unparseable judge reply: {res.text[:120]!r}"
    return verdict, str(obj.get("reason", ""))
