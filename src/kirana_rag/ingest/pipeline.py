"""ingest(pdf_path) -> doc_id. Writes pages.jsonl, chunks.jsonl, vision/*.png, meta.json to .cache."""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from .. import config
from . import images, tables
from .chunk import Chunk, group_paragraphs, make_header
from .pdf import (
    PageRecord,
    doc_title,
    is_footnote,
    is_heading,
    read_pages,
    reading_order,
    strip_headers_footers,
)

DECORATIVE_MAX_WORDS = 15


@dataclass
class PageSummary:
    page: int
    text_chunks: int = 0
    tables: int = 0
    images: int = 0
    vlm_tokens: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class IngestResult:
    doc_id: str
    title: str
    chunks: list[Chunk]
    summary: list[PageSummary]
    cached: bool = False


def slugify(stem: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


def make_doc_id(pdf_path: Path) -> str:
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()[:8]
    return f"{slugify(pdf_path.stem)}-{digest}"


def doc_dir(doc_id: str) -> Path:
    return config.CACHE_DIR / doc_id


def load_chunks(doc_id: str) -> list[Chunk]:
    path = doc_dir(doc_id) / "chunks.jsonl"
    return [Chunk.from_dict(json.loads(line)) for line in path.read_text().splitlines() if line]


def list_doc_ids() -> list[str]:
    if not config.CACHE_DIR.exists():
        return []
    return sorted(p.name for p in config.CACHE_DIR.iterdir() if (p / "chunks.jsonl").exists())


def ingest(pdf_path: Path, force: bool = False) -> IngestResult:
    """Ingest one PDF. Re-running on the same bytes is served from .cache."""
    doc_id = make_doc_id(pdf_path)
    out = doc_dir(doc_id)
    meta_path = out / "meta.json"
    if meta_path.exists() and not force:
        meta = json.loads(meta_path.read_text())
        summary = [PageSummary(**s) for s in meta["summary"]]
        return IngestResult(doc_id, meta["title"], load_chunks(doc_id), summary, cached=True)

    out.mkdir(parents=True, exist_ok=True)
    (out / "vision").mkdir(exist_ok=True)
    doc = pymupdf.open(pdf_path)
    pages, body_size = read_pages(doc)
    removed = strip_headers_footers(pages)
    title = doc_title(doc, pages, pdf_path.stem)
    _write_pages(out / "pages.jsonl", pages)

    summaries = {p.number: PageSummary(p.number) for p in pages}
    tables_by_page = {p.number: tables.extract_tables(doc[p.number - 1]) for p in pages}
    tables.merge_continued(tables_by_page)
    # a merged table also occupies its continuation pages; its blocks there are not prose
    table_regions: dict[int, list[tuple[float, float, float, float]]] = {}
    for tlist in tables_by_page.values():
        for t in tlist:
            for part_page, bbox in t.parts or []:
                table_regions.setdefault(part_page, []).append(bbox)

    chunks: list[Chunk] = []
    section = ""
    for rec in pages:
        page = doc[rec.number - 1]
        sm = summaries[rec.number]
        consumed: set[int] = set()  # ids of blocks that belong to a table, figure or caption
        figure_regions = images.select_regions(page, rec.text_chars)
        rec.blocks = reading_order(
            rec,
            table_regions.get(rec.number, []) + [r.bbox for r in figure_regions],
        )
        headings = [
            (b.bbox[1], " ".join(b.text.split())) for b in rec.blocks if is_heading(b, body_size)
        ]

        def section_at(y: float, carried: str = section, headings=headings) -> str:
            above = [h for top, h in headings if top <= y]
            return above[-1] if above else carried

        for bbox in table_regions.get(rec.number, []):
            consumed |= {id(b) for b in images.blocks_inside(rec, bbox)}

        counters = {"t": 0, "f": 0, "x": 0, "s": 0}

        def next_id(letter: str, n: int = rec.number, counters=counters) -> str:
            counters[letter] += 1
            return f"p{n}-{letter}{counters[letter]}"

        for t in tables_by_page[rec.number]:
            cap = images.find_caption(rec.blocks, t.bbox, table=True)
            caption = " ".join(cap.text.split()) if cap else ""
            if cap and len(cap.text.split()) <= 40:
                consumed.add(id(cap))
            pgs = t.pages or [t.page]
            sec = section_at(t.bbox[1])
            chunks.append(
                Chunk(
                    next_id("t"),
                    doc_id,
                    pgs,
                    "table",
                    sec,
                    caption,
                    list(t.bbox),
                    tables.to_markdown(t.rows),
                    make_header(title, pgs, "table", caption or sec),
                )
            )
            sm.tables += 1

        for region in figure_regions:
            inside = images.blocks_inside(rec, region.bbox)
            consumed |= {id(b) for b in inside}
            cap = images.find_caption(rec.blocks, region.bbox)
            caption = " ".join(cap.text.split()) if cap else ""
            if cap and len(cap.text.split()) <= 40:
                consumed.add(id(cap))
            png = images.render_crop(page, region.bbox)
            cid = next_id("s" if region.kind == "scan" else "f")
            (out / "vision" / f"{cid}.png").write_bytes(png)
            chunk = _figure_chunk(
                cid, doc_id, rec, region, caption, section_at(region.bbox[1], ""), title, png
            )
            sm.images += 1
            if chunk.text:
                chunks.append(chunk)
            sm.vlm_tokens += chunk.vlm_tokens
            sm.warnings += chunk.warnings

        prose: list = []
        notes: list = []
        for b in rec.blocks:
            if id(b) in consumed:
                continue
            if is_footnote(b, rec):
                notes.append(b)
            elif is_heading(b, body_size):
                _flush_prose(prose, chunks, doc_id, rec, section, title, next_id, sm)
                prose = []
                section = " ".join(b.text.split())
            else:
                prose.append(b)
        _flush_prose(prose, chunks, doc_id, rec, section, title, next_id, sm)
        for note in notes:  # each footnote stands alone, with its marker
            chunks.append(_list_chunk(next_id("x"), doc_id, rec, [note], section, title))
            sm.text_chunks += 1

        if not any(rec.number in c.pages for c in chunks):
            sm.warnings.append("nothing extractable on this page")
    summary = [summaries[n] for n in sorted(summaries)]
    chunks.sort(key=lambda c: (c.pages[0], c.bbox[1] if c.bbox else 0))
    (out / "chunks.jsonl").write_text("".join(json.dumps(c.to_dict()) + "\n" for c in chunks))
    meta_path.write_text(
        json.dumps(
            {
                "doc_id": doc_id,
                "title": title,
                "source": pdf_path.name,
                "n_pages": len(pages),
                "header_footer_blocks_removed": removed,
                "summary": [s.__dict__ for s in summary],
            },
            indent=2,
        )
    )
    return IngestResult(doc_id, title, chunks, summary)


def _list_chunk(cid, doc_id, rec: PageRecord, blocks, section, title) -> Chunk:
    """One text chunk from whole blocks, one line per source line (contents lists, footnotes)."""
    bbox = [
        min(b.bbox[0] for b in blocks),
        min(b.bbox[1] for b in blocks),
        max(b.bbox[2] for b in blocks),
        max(b.bbox[3] for b in blocks),
    ]
    text = "\n".join(b.text for b in blocks)
    return Chunk(
        cid,
        doc_id,
        [rec.number],
        "text",
        section,
        "",
        bbox,
        text,
        make_header(title, [rec.number], "text", section),
    )


def _flush_prose(blocks, chunks, doc_id, rec: PageRecord, section, title, next_id, sm) -> None:
    if not blocks:
        return
    y0 = min(b.bbox[1] for b in blocks)
    x0 = min(b.bbox[0] for b in blocks)
    x1 = max(b.bbox[2] for b in blocks)
    y1 = max(b.bbox[3] for b in blocks)
    for text in group_paragraphs(blocks):
        chunks.append(
            Chunk(
                next_id("x"),
                doc_id,
                [rec.number],
                "text",
                section,
                "",
                [x0, y0, x1, y1],
                text,
                make_header(title, [rec.number], "text", section),
            )
        )
        sm.text_chunks += 1


def _figure_chunk(cid, doc_id, rec, region, caption, section, title, png) -> Chunk:
    warnings: list[str] = []
    tokens = 0
    try:
        res = images.transcribe(png)
        text, tokens = res.text.strip(), res.tokens_in + res.tokens_out
    except RuntimeError as e:
        text = ""
        warnings.append(f"vision failed: {e}")
    if "[unreadable]" in text:
        warnings.append("transcript contains [unreadable]")
    if text and len(text.split()) <= DECORATIVE_MAX_WORDS and not re.search(r"\d", text):
        warnings.append("short transcript with no numbers: possibly decorative")
    kind = region.kind
    label = caption or section
    body = f"{caption}\n\n{text}" if caption and caption not in text else text
    return Chunk(
        cid,
        doc_id,
        [rec.number],
        kind,
        section,
        caption,
        list(region.bbox),
        body,
        make_header(title, [rec.number], kind, label),
        warnings,
        tokens,
    )


def _write_pages(path: Path, pages: list[PageRecord]) -> None:
    with path.open("w") as f:
        for p in pages:
            f.write(
                json.dumps(
                    {
                        "page": p.number,
                        "width": p.width,
                        "height": p.height,
                        "blocks": [
                            {"bbox": b.bbox, "size": b.size, "text": b.text} for b in p.blocks
                        ],
                    }
                )
                + "\n"
            )
