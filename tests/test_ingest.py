import pymupdf

from kirana_rag import config
from kirana_rag.ingest import images, pipeline, tables
from kirana_rag.ingest.chunk import group_paragraphs, tokens
from kirana_rag.ingest.pdf import (
    Block,
    navigation_groups,
    read_pages,
    reading_order,
    strip_headers_footers,
)

from .pdfmaker import build_layout_pdf, build_pdf

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


LEFT, MID, RIGHT = (57, 215), (215, 380), (380, 538)


def _paras(prefix: str, n: int, reps: int = 4) -> list[str]:
    return [
        f"{prefix}{i} " + "lorem ipsum dolor sit amet consectetur " * reps for i in range(1, n + 1)
    ]


def _ordered_prefixes(path, regions=()):
    doc = pymupdf.open(path)
    pages, _ = read_pages(doc)
    rec = pages[0]
    return [b.text.split()[0] for b in reading_order(rec, list(regions)) if "Acme" not in b.text]


def _column_items(cols, top=100, step=90, width_edge=0, reps=4):
    items = []
    for (x0, x1), prefix in cols:
        for i, text in enumerate(_paras(prefix, 3, reps)):
            items.append((x0, top + i * step, x1 - width_edge, text, 10))
    return items


def test_three_column_page_reads_column_by_column(tmp_path):
    pdf = tmp_path / "c.pdf"
    items = _column_items([(LEFT, "Aa"), (MID, "Bb"), (RIGHT, "Cc")], width_edge=12)
    build_layout_pdf(pdf, [items])
    assert _ordered_prefixes(pdf) == ["Aa1", "Aa2", "Aa3", "Bb1", "Bb2", "Bb3", "Cc1", "Cc2", "Cc3"]


def test_two_columns_with_full_width_heading_and_table_form_bands(tmp_path):
    pdf = tmp_path / "c.pdf"
    wide = [(57, 60, 538, "Tessellate full width heading", 16)]
    top = _column_items([((57, 280), "La"), ((310, 538), "Ra")], top=100, step=30, reps=1)
    table_y = 240
    below = _column_items([((57, 280), "Lb"), ((310, 538), "Rb")], top=330, step=30, reps=1)
    build_layout_pdf(pdf, [wide + top + below])
    got = _ordered_prefixes(pdf, regions=[(57, table_y, 538, 320)])
    assert got == ["Tessellate", "La1", "La2", "La3", "Ra1", "Ra2", "Ra3"] + [
        "Lb1",
        "Lb2",
        "Lb3",
        "Rb1",
        "Rb2",
        "Rb3",
    ]


def test_two_columns_without_enough_blocks_keep_the_old_order(tmp_path):
    pdf = tmp_path / "c.pdf"
    items = _column_items([((57, 280), "Ld"), ((310, 538), "Rd")], top=100, step=60, reps=1)
    items = items[:3] + items[3:5]  # right column has only 2 blocks: not sure, so unchanged
    build_layout_pdf(pdf, [items])
    got = _ordered_prefixes(pdf)
    assert got == ["Ld1", "Rd1", "Ld2", "Rd2", "Ld3"]


def test_single_column_page_order_is_unchanged(tmp_path):
    pdf = tmp_path / "c.pdf"
    build_layout_pdf(pdf, [[(57, 100 + i * 70, 538, t, 10) for i, t in enumerate(_paras("Zs", 5))]])
    doc = pymupdf.open(pdf)
    pages, _ = read_pages(doc)
    assert reading_order(pages[0], []) is pages[0].blocks


def test_columns_through_the_pipeline_keep_a_sentence_together(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    pdf = tmp_path / "c.pdf"
    items = _column_items([((57, 280), "Pa"), ((310, 538), "Pb")], top=100, step=90)
    build_layout_pdf(pdf, [items])
    res = pipeline.ingest(pdf, force=True)
    text = "\n".join(c.text for c in res.chunks)
    assert text.index("Pa3") < text.index("Pb1")


def _footnote_pdf(path, note: str, size: float = 7.5):
    body = [(57, 100 + i * 80, 538, t, 10) for i, t in enumerate(_paras("Fn", 3))]
    build_layout_pdf(path, [body + [(57, 700, 400, note, size)]])


def test_footnote_becomes_its_own_chunk_on_a_page_without_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    pdf = tmp_path / "f.pdf"
    _footnote_pdf(pdf, "\u00b9 Ombra figures exclude one site.")
    res = pipeline.ingest(pdf, force=True)
    notes = [c for c in res.chunks if "Ombra" in c.text]
    assert len(notes) == 1 and notes[0].text.startswith("\u00b9") and notes[0].type == "text"
    assert "Fn3" not in notes[0].text


def test_small_text_without_marker_or_with_body_size_is_not_a_footnote(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    for note, size in [
        ("Source: Ombra figures exclude one site.", 7.5),
        ("1 Ombra at body size.", 10),
    ]:
        pdf = tmp_path / f"f{size}.pdf"
        _footnote_pdf(pdf, note, size)
        res = pipeline.ingest(pdf, force=True)
        (c,) = [c for c in res.chunks if "Ombra" in c.text]
        assert "Fn3" in c.text  # still merged with the prose, as before


def test_table_over_four_pages_is_one_chunk(tmp_path):
    pdf = tmp_path / "t.pdf"
    build_pdf(
        pdf,
        [
            {"table": (570, [HEADER] + _rows(10))},
            {"table": (70, [HEADER] + _rows(35, 10))},
            {"table": (70, [HEADER] + _rows(35, 45))},
            {"table": (70, [HEADER] + _rows(5, 80))},
        ],
    )
    by_page = _extract(pdf)
    tables.merge_continued(by_page)
    (t,) = [t for ts in by_page.values() for t in ts]
    assert t.pages == [1, 2, 3, 4] and len(t.rows) == 1 + 10 + 35 + 35 + 5


def test_table_run_stops_when_a_middle_page_ends_high(tmp_path):
    pdf = tmp_path / "t.pdf"
    build_pdf(
        pdf,
        [
            {"table": (570, [HEADER] + _rows(10))},
            {"table": (70, [HEADER] + _rows(4, 10))},  # ends in the upper half: the table is over
            {"table": (70, [HEADER] + _rows(5, 14))},
        ],
    )
    by_page = _extract(pdf)
    tables.merge_continued(by_page)
    assert [len(by_page[n]) for n in (1, 2, 3)] == [1, 0, 1]


def test_contents_list_is_one_text_chunk_not_a_table(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    pdf = tmp_path / "n.pdf"
    entries = [f"Part {c} {'.' * 60} {i * 3}" for i, c in enumerate("ABCDEFGH", 1)]
    build_layout_pdf(pdf, [[(57, 100 + i * 20, 538, e, 10) for i, e in enumerate(entries)]])
    res = pipeline.ingest(pdf, force=True)
    (c,) = [c for c in res.chunks if "Part A" in c.text]
    assert c.type == "text" and c.text.count("\n") == len(entries) - 1 and "Part H" in c.text


def test_navigation_needs_most_lines_to_end_in_a_page_number():
    mk = lambda t: Block((0, 0, 1, 1), t, 10.0)
    prose = [mk("A sentence that ends in a year 2024."), mk("Another one with no leader.")]
    nav = [mk(f"Item {i} {'.' * 20} {i}") for i in range(1, 5)]
    assert navigation_groups(prose) == []
    assert len(navigation_groups(prose + nav + prose)) == 1
    assert navigation_groups(nav[:2]) == []  # too short to be a list
    leader_free = [mk(f"Item {i}      {i}") for i in range(1, 5)]
    assert len(navigation_groups(leader_free)) == 1


def test_header_band_is_folded_only_when_it_is_a_band():
    band = [
        ["Site", "Inpatient", "", "Outpatient", ""],
        ["", "Elective", "Day", "First", "Repeat"],
        ["A1", "10", "20", "30", "40"],
    ]
    folded = tables.fold_header_band(band)
    assert folded[0] == [
        "Site",
        "Inpatient / Elective",
        "Inpatient / Day",
        "Outpatient / First",
        "Outpatient / Repeat",
    ]
    assert len(folded) == 2 and folded[1][0] == "A1"
    plain = [["Site", "Qty", "Area"], ["A1", "10", "20"], ["B2", "30", "40"]]
    assert tables.fold_header_band(plain) == plain
    numbers = [["Site", "", "Total"], ["", "10", "20"], ["B2", "30", "40"]]
    assert tables.fold_header_band(numbers) == numbers  # the second row is data, not labels
