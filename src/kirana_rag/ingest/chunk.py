"""Chunk dataclass and prose chunking."""

import re
from dataclasses import asdict, dataclass, field

from .pdf import Block

TARGET_TOKENS = 300
MAX_TOKENS = 450
OVERLAP_TOKENS = 40


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    pages: list[int]
    type: str  # text | table | figure | scan
    section: str
    caption: str
    bbox: list[float]
    text: str
    header: str = ""
    warnings: list[str] = field(default_factory=list)
    vlm_tokens: int = 0

    @property
    def indexed_text(self) -> str:
        """Header + body: what BM25 sees and what the LLM is shown."""
        return f"{self.header}\n{self.text}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Chunk":
        return cls(**d)


def tokens(text: str) -> int:
    """Rough token estimate: words * 1.3."""
    return int(len(text.split()) * 1.3) + 1


def make_header(doc_title: str, pages: list[int], kind: str, label: str) -> str:
    span = f"p{pages[0]}" if len(pages) == 1 else f"p{pages[0]}-{pages[-1]}"
    return (
        f"[{doc_title} | {span} | {kind}: {label}]" if label else f"[{doc_title} | {span} | {kind}]"
    )


def _split_long(paragraph: str) -> list[str]:
    """Split one oversize paragraph on sentence boundaries with a small token overlap."""
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    parts: list[str] = []
    cur: list[str] = []
    for s in sentences:
        if cur and tokens(" ".join(cur + [s])) > TARGET_TOKENS:
            parts.append(" ".join(cur))
            tail: list[str] = []
            while cur and tokens(" ".join([cur[-1]] + tail)) <= OVERLAP_TOKENS:
                tail.insert(0, cur.pop())
            cur = tail
        cur.append(s)
    if cur:
        parts.append(" ".join(cur))
    return parts


def group_paragraphs(blocks: list[Block]) -> list[str]:
    """Greedy-pack paragraphs into chunks of about TARGET_TOKENS; split only oversize ones."""
    units: list[str] = []
    for b in blocks:
        para = " ".join(b.text.split())
        units.extend(_split_long(para) if tokens(para) > MAX_TOKENS else [para])
    groups: list[list[str]] = []
    cur: list[str] = []
    for u in units:
        if cur and tokens(" ".join(cur + [u])) > TARGET_TOKENS:
            groups.append(cur)
            cur = []
        cur.append(u)
    if cur:
        groups.append(cur)
    return ["\n\n".join(g) for g in groups]
