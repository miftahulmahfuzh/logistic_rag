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
# a block wider than this share of the page spans it: heading, caption or table, not a column
FULL_WIDTH_FRAC = 0.7
COLUMN_GAP_FRAC = 0.05  # columns overlap by less than this share of the page width
COLUMN_MIN_BLOCKS = 3
COLUMN_MAX = 3
FOOTNOTE_BOTTOM_FRAC = 0.25  # a footnote sits in the bottom quarter of the page ...
FOOTNOTE_SIZE_RATIO = 0.85  # ... and is set at most this much of the body size
NAV_MIN_LINES = 3
NAV_LINE_SHARE = 0.6
# a footnote opens with a marker: superscript digits or a symbol (text may follow directly), or plain digits then a space
FOOTNOTE_RE = re.compile(
    r"^\s*(?:(?:[\u00b9\u00b2\u00b3\u2070-\u2079]+|[*\u2020\u2021\u00a7\u00b6])\s*|\d{1,2}[.)]?\s+)[^\W\d_]"
)
# a navigation line: some text, a run of dot leaders or wide spaces, then a short page number
NAV_LINE_RE = re.compile(
    r"\S.*?(?:[.\u00b7\u2026](?:\s?[.\u00b7\u2026]){2,}|\s{3,})\s*(?:\d{1,4}|[ivxlc]{1,6})\s*$"
)
PAGE_NUMBER_RE = re.compile(r"^\s*(?:\d{1,4}|[ivxlc]{1,6})\s*$")


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


def centre_inside(inner: tuple, outer: tuple) -> bool:
    cx, cy = (inner[0] + inner[2]) / 2, (inner[1] + inner[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def _column_groups(blocks: list[Block], page_width: float) -> list[list[Block]] | None:
    """Group narrow blocks by x-range; None unless there are 2 to 3 groups of at least 3 blocks each."""
    tol = COLUMN_GAP_FRAC * page_width
    groups: list[list[Block]] = []
    right = 0.0
    for b in sorted(blocks, key=lambda b: b.bbox[0]):
        overlap = min(b.bbox[2], right) - b.bbox[0]
        if groups and overlap >= min(tol, (b.bbox[2] - b.bbox[0]) / 2):
            groups[-1].append(b)
            right = max(right, b.bbox[2])
        else:
            groups.append([b])
            right = b.bbox[2]
    if not 2 <= len(groups) <= COLUMN_MAX or any(len(g) < COLUMN_MIN_BLOCKS for g in groups):
        return None
    return groups


def reading_order(page: PageRecord, regions: list[tuple]) -> list[Block]:
    """Blocks in reading order: column by column in bands between full-width blocks, else y then x.

    `regions` are table and figure boxes. Blocks inside them are not columns of prose, and a
    full-width region ends a band like a full-width block does. Footnotes are not columns either
    (one can span the gutter and would merge the column groups); they follow the columns of their
    band. Unsure means the existing order.
    """
    inside_ids = {
        id(b)
        for b in page.blocks
        if is_footnote(b, page) or any(centre_inside(b.bbox, r) for r in regions)
    }
    free = [b for b in page.blocks if id(b) not in inside_ids]

    def wide(box: tuple) -> bool:
        return box[2] - box[0] > FULL_WIDTH_FRAC * page.width

    narrow = [b for b in free if not wide(b.bbox)]
    groups = _column_groups(narrow, page.width)
    if groups is None:
        return page.blocks
    column_of = {id(b): i for i, g in enumerate(groups) for b in g}
    seps = [b.bbox for b in free if wide(b.bbox)] + [r for r in regions if wide(r)]
    seps_y = sorted((box[1] + box[3]) / 2 for box in seps)

    def band(box: tuple) -> int:
        return sum(1 for y in seps_y if y < (box[1] + box[3]) / 2)

    full = {id(b) for b in free if wide(b.bbox)}
    ordered: list[Block] = []
    for i in range(len(seps_y) + 1):
        in_band = [b for b in page.blocks if band(b.bbox) == i]
        ordered += [b for b in in_band if id(b) in full]
        for col in range(len(groups)):
            ordered += [b for b in in_band if column_of.get(id(b)) == col]
        ordered += [b for b in in_band if id(b) in inside_ids]
    return ordered


def body_size(page: PageRecord) -> float:
    """The font size most of this page's text is set in (median over characters)."""
    sizes = sorted((b.size, len(b.text)) for b in page.blocks)
    half = sum(n for _, n in sizes) / 2
    seen = 0
    for size, n in sizes:
        seen += n
        if seen >= half:
            return size
    return 0.0


def is_footnote(b: Block, page: PageRecord) -> bool:
    """Small text in the bottom quarter of the page that opens with a note marker."""
    return (
        b.bbox[1] >= page.height * (1 - FOOTNOTE_BOTTOM_FRAC)
        and b.size <= body_size(page) * FOOTNOTE_SIZE_RATIO
        and bool(FOOTNOTE_RE.match(b.text))
    )


def _entries(text: str) -> list[str]:
    """Lines of a block, with a line that is only a page number joined to the line before it."""
    out: list[str] = []
    for line in text.splitlines():
        if out and PAGE_NUMBER_RE.match(line):
            out[-1] += " " + line.strip()
        else:
            out.append(line)
    return out


def navigation_groups(blocks: list[Block]) -> list[list[Block]]:
    """Runs of consecutive blocks whose lines mostly end in a leader and a page number (a contents list)."""
    runs: list[list[Block]] = []
    cur: list[Block] = []
    for b in blocks:
        if any(NAV_LINE_RE.search(line) for line in _entries(b.text)):
            cur.append(b)
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    out = []
    for run in runs:
        lines = [line for b in run for line in _entries(b.text)]
        hits = sum(1 for line in lines if NAV_LINE_RE.search(line))
        if len(lines) >= NAV_MIN_LINES and hits >= NAV_LINE_SHARE * len(lines):
            out.append(run)
    return out
