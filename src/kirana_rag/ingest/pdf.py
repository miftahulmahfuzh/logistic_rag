"""Page records: text blocks with font sizes, header/footer stripping, heading detection."""

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

import pymupdf

CAPTION_RE = re.compile(r"^\s*(Figure|Fig\.|Chart|Table)\s*\d+", re.IGNORECASE)
EDGE_FRAC = 0.12  # header/footer lines live in the top/bottom 12% of the page
HEADING_RATIO = 1.2
HEADING_MAX_WORDS = 15


@dataclass
class Block:
    bbox: tuple[float, float, float, float]
    text: str
    size: float  # largest span font size in the block


@dataclass
class PageRecord:
    number: int  # 1-based
    width: float
    height: float
    blocks: list[Block] = field(default_factory=list)

    @property
    def text_chars(self) -> int:
        return sum(len(b.text) for b in self.blocks)


def read_pages(doc: pymupdf.Document) -> tuple[list[PageRecord], float]:
    """Read every page into text blocks in reading order. Returns pages and the body font size."""
    pages: list[PageRecord] = []
    sizes: Counter[float] = Counter()
    for page in doc:
        rec = PageRecord(page.number + 1, page.rect.width, page.rect.height)
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            lines, top = [], 0.0
            for line in b["lines"]:
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                lines.append("".join(s["text"] for s in line["spans"]).strip())
                for s in spans:
                    top = max(top, s["size"])
                    sizes[round(s["size"], 1)] += len(s["text"])
            if lines:
                rec.blocks.append(Block(tuple(b["bbox"]), "\n".join(lines), round(top, 1)))
        rec.blocks.sort(key=lambda blk: (round(blk.bbox[1]), blk.bbox[0]))
        pages.append(rec)
    expanded = [size for size, n in sizes.items() for _ in range(n)]
    body = statistics.median(expanded) if expanded else 10.0
    return pages, body


def _norm_line(text: str) -> str:
    return re.sub(r"\d+", "#", " ".join(text.lower().split()))


def strip_headers_footers(pages: list[PageRecord]) -> int:
    """Drop blocks near a page edge whose digit-normalised text repeats on >= 50% of pages."""
    counts: Counter[str] = Counter()
    for p in pages:
        seen = {_norm_line(b.text) for b in p.blocks if _at_edge(b, p)}
        counts.update(seen)
    min_pages = max(2, len(pages) / 2)
    repeated = {k for k, n in counts.items() if n >= min_pages}
    removed = 0
    for p in pages:
        keep = [b for b in p.blocks if not (_at_edge(b, p) and _norm_line(b.text) in repeated)]
        removed += len(p.blocks) - len(keep)
        p.blocks = keep
    return removed


def _at_edge(b: Block, p: PageRecord) -> bool:
    return b.bbox[3] <= p.height * EDGE_FRAC or b.bbox[1] >= p.height * (1 - EDGE_FRAC)


def is_heading(b: Block, body_size: float) -> bool:
    """A short block set noticeably larger than body text, and not a figure/table caption."""
    return (
        b.size >= body_size * HEADING_RATIO
        and len(b.text.split()) <= HEADING_MAX_WORDS
        and not CAPTION_RE.match(b.text)
    )


def doc_title(doc: pymupdf.Document, pages: list[PageRecord], fallback: str) -> str:
    """PDF metadata title if present, else the largest text on the first page."""
    meta = (doc.metadata or {}).get("title", "").strip()
    if meta:
        return meta
    if pages and pages[0].blocks:
        biggest = max(pages[0].blocks, key=lambda b: b.size)
        return " ".join(biggest.text.split())
    return fallback
