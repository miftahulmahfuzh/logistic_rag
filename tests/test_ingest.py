import pymupdf

from kirana_rag import config
from kirana_rag.ingest import images, pipeline, tables
from kirana_rag.ingest.chunk import group_paragraphs, tokens
from kirana_rag.ingest.pdf import Block, read_pages, strip_headers_footers

from .pdfmaker import build_pdf

HEADER = ["Code", "Site", "Area"]


def _rows(n: int, start: int = 0) -> list[list[str]]:
    return [[f"C{i}", f"Site {i}", f"{i}00"] for i in range(start, start + n)]


def _two_page_table_pdf(path, header2=HEADER):
    build_pdf(
        path,
        [
            {"text": [(80, "Table 9. Sites", 11)], "table": (570, [HEADER] + _rows(10))},
            {"table": (70, [header2] + _rows(5, 10))},
        ],
    )


def _extract(path):
    doc = pymupdf.open(path)
    return {p.number + 1: tables.extract_tables(p) for p in doc}


def test_table_continuation_merges_and_drops_repeated_header(tmp_path):
    pdf = tmp_path / "t.pdf"
    _two_page_table_pdf(pdf)
    by_page = _extract(pdf)
    tables.merge_continued(by_page)
    assert by_page[2] == []
    (t,) = by_page[1]
    assert t.pages == [1, 2]
    assert len(t.rows) == 1 + 15  # one header, 15 data rows
    assert sum(r == HEADER for r in t.rows) == 1


def test_continued_table_is_not_repeated_as_prose(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    pdf = tmp_path / "t.pdf"
    _two_page_table_pdf(pdf)
    res = pipeline.ingest(pdf, force=True)
    (table,) = [c for c in res.chunks if c.type == "table"]
    assert table.pages == [1, 2]
    assert "Site 14" in table.text
    prose = [c for c in res.chunks if c.type == "text" and 2 in c.pages]
    cells = {cell for r in _rows(5, 10) for cell in r}
    assert not any(cell in c.text for c in prose for cell in cells)


def test_table_with_different_header_is_not_merged(tmp_path):
    pdf = tmp_path / "t.pdf"
    _two_page_table_pdf(pdf, header2=["Code", "Place", "Area"])
    by_page = _extract(pdf)
    tables.merge_continued(by_page)
    assert len(by_page[1]) == 1 and len(by_page[2]) == 1


def test_table_markdown_keeps_cells():
    md = tables.to_markdown([["A", "B"], ["1,000", "x"]])
    assert md.splitlines()[0] == "| A | B |"
    assert "| 1,000 | x |" in md


def test_header_footer_stripped_only_when_repeated(tmp_path):
    pdf = tmp_path / "h.pdf"
    build_pdf(pdf, [{"text": [(100, f"Body text unique {i}", 10)]} for i in range(4)])
    pages, _ = read_pages(pymupdf.open(pdf))
    removed = strip_headers_footers(pages)
    assert removed == 4
    assert all("Acme" not in b.text for p in pages for b in p.blocks)
    assert all(any("Body text" in b.text for b in p.blocks) for p in pages)


def test_caption_linking_picks_nearest_and_right_kind():
    blocks = [
        Block((50, 100, 300, 112), "Figure 3. Network", 10),
        Block((50, 400, 300, 412), "Table 2. Sites", 10),
        Block((50, 600, 300, 612), "Figure 9. Far away", 10),
    ]
    img = (50, 120, 300, 390)
    assert images.find_caption(blocks, img).text.startswith("Figure 3")
    assert images.find_caption(blocks, img, table=True).text.startswith("Table 2")
    assert images.find_caption(blocks, (50, 700, 300, 790)) is None


def test_select_regions_skips_tiny_images_and_flags_scan(tmp_path):
    pdf = tmp_path / "i.pdf"
    build_pdf(
        pdf,
        [
            {"text": [(100, "word " * 80, 10)], "image": (50, 50, 80, 70)},  # logo-sized
            {"text": [(100, "word " * 80, 10)], "image": (50, 150, 500, 450)},  # figure
            {"image": (0, 0, 595, 842)},  # scan: no text
        ],
    )
    doc = pymupdf.open(pdf)
    assert images.select_regions(doc[0], 400) == []
    (fig,) = images.select_regions(doc[1], 400)
    assert fig.kind == "figure"
    (scan,) = images.select_regions(doc[2], 0)
    assert scan.kind == "scan"


def test_prose_grouping_respects_target_and_splits_long_paragraph():
    short = [Block((0, i, 1, 2), "word " * 100, 10) for i in range(4)]
    groups = group_paragraphs(short)
    assert len(groups) > 1 and all(tokens(g) <= 450 for g in groups)
    long = [Block((0, 0, 1, 2), ("A sentence with some words. " * 120), 10)]
    parts = group_paragraphs(long)
    assert len(parts) > 1 and all(tokens(p) <= 450 for p in parts)
