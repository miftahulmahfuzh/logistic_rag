"""Prompt build, LLM call, robust JSON parsing, and the code-based citation verifier."""

import json
import re
import time
from dataclasses import dataclass, field

from . import config, llm, prompts
from .ingest.chunk import Chunk
from .retrieve import Hit, Index

VALID_STATUS = {"answered", "refused", "conflict"}


@dataclass
class Citation:
    chunk_id: str
    page: int | None
    quote: str
    verified: bool = False
    reason: str = ""


@dataclass
class Answer:
    question: str
    status: str = "error"
    answer: str = ""
    citations: list[Citation] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    retrieval_ms: float = 0.0
    llm_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float | None = None
    error: str = ""


def chunk_refs(chunks: list[Chunk]) -> dict[str, Chunk]:
    """Reference id the model cites -> chunk. Qualified with doc_id only if ids collide."""
    ids = [c.chunk_id for c in chunks]
    return {
        (c.chunk_id if ids.count(c.chunk_id) == 1 else f"{c.doc_id}/{c.chunk_id}"): c
        for c in chunks
    }


def format_context(chunks: list[Chunk]) -> str:
    parts = []
    for ref, c in chunk_refs(chunks).items():
        pages = ",".join(map(str, c.pages))
        label = c.caption or c.section or "-"
        parts.append(f"[{ref} | {c.doc_id} | pages {pages} | {c.type} | {label}]\n{c.text}")
    return "\n\n---\n\n".join(parts)


def parse_json(raw: str) -> dict | None:
    """Parse a model reply as JSON: strips code fences, falls back to the outermost braces."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    for candidate in (text, text[text.find("{") : text.rfind("}") + 1]):
        try:
            obj = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


def normalise(text: str) -> str:
    """Lowercase, drop commas and markdown pipes/emphasis, collapse whitespace."""
    text = re.sub(r"[,|*`_]", "", text.lower())
    return " ".join(text.split())


def verify_citation(cit: Citation, retrieved: dict[str, Chunk]) -> Citation:
    """Code check: chunk was retrieved, page belongs to it, quote is verbatim in its text."""
    chunk = retrieved.get(cit.chunk_id)
    if chunk is None:
        cit.reason = "chunk_id not among retrieved chunks"
    elif cit.page not in chunk.pages:
        cit.reason = f"page {cit.page} not in chunk pages {chunk.pages}"
    elif not cit.quote.strip():
        cit.reason = "empty quote"
    elif normalise(cit.quote) not in normalise(chunk.indexed_text):
        cit.reason = "quote not found verbatim in chunk"
    else:
        cit.verified = True
    return cit


def _citations(obj: dict) -> list[Citation]:
    out = []
    for c in obj.get("citations") or []:
        if not isinstance(c, dict):
            continue
        page = c.get("page")
        out.append(
            Citation(
                str(c.get("chunk_id", "")),
                page if isinstance(page, int) else None,
                str(c.get("quote", "")),
            )
        )
    return out


def answer_question(question: str, chunks: list[Chunk], model_max_tokens: int = 800) -> Answer:
    """Answer from the given chunks only. Used by ask (retrieved chunks) and eval (oracle chunks)."""
    ans = Answer(question)
    prompt = prompts.ANSWER_USER.format(context=format_context(chunks), question=question)
    t0 = time.perf_counter()
    res = llm.complete(prompt, system=prompts.ANSWER_SYSTEM, max_tokens=model_max_tokens)
    tokens_in, tokens_out = res.tokens_in, res.tokens_out
    obj = parse_json(res.text)
    if obj is None:  # one repair retry
        fix = llm.complete(prompts.REPAIR_USER.format(raw=res.text), max_tokens=model_max_tokens)
        tokens_in, tokens_out = tokens_in + fix.tokens_in, tokens_out + fix.tokens_out
        obj = parse_json(fix.text)
    ans.llm_ms = (time.perf_counter() - t0) * 1000
    ans.tokens_in, ans.tokens_out = tokens_in, tokens_out
    ans.cost = config.estimate_cost(config.settings().model, tokens_in, tokens_out)
    if obj is None:
        ans.error = "could not parse model reply as JSON"
        return ans
    status = str(obj.get("status", "")).lower()
    if status not in VALID_STATUS:
        ans.error = f"invalid status {status!r} in model reply"
        return ans
    ans.status = status
    ans.answer = str(obj.get("answer", ""))
    ans.citations = [verify_citation(c, chunk_refs(chunks)) for c in _citations(obj)]
    return ans


def ask(question: str, index: Index, k: int = config.DEFAULT_TOP_K) -> Answer:
    t0 = time.perf_counter()
    hits = index.search(question, k)
    retrieval_ms = (time.perf_counter() - t0) * 1000
    ans = answer_question(question, [h.chunk for h in hits])
    ans.hits, ans.retrieval_ms = hits, retrieval_ms
    return ans
