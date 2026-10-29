"""Text-layer tables: find_tables -> cell grid -> markdown, with cross-page merging."""

import re
from collections.abc import Callable
from dataclasses import dataclass

import pymupdf

MERGE_BOTTOM_FRAC = 0.6  # a table that continues must end low on its page ...
MERGE_TOP_FRAC = 0.4  # ... and the next one must start high on the next page


@dataclass
class Table:
    page: int
    bbox: tuple[float, float, float, float]
    rows: list[list[str]]  # rows[0] is the header
    page_height: float
    caption: str = ""
    pages: list[int] | None = None
    parts: list[tuple[int, tuple[float, float, float, float]]] | None = None  # (page, bbox) each

    def __post_init__(self) -> None:
        if self.pages is None:
            self.pages = [self.page]
        if self.parts is None:
            self.parts = [(self.page, self.bbox)]


NUMBER_RE = re.compile(r"^[\d.,\-\u2013%()\u00a3$\u20ac\s]+$")


def _clean(s: str) -> str:
    return " ".join(s.split()).replace("|", "/")


def extract_tables(page: pymupdf.Page) -> list[Table]:
    """Find tables on a page; cell text is read per cell rectangle so numbers stay intact."""
    out: list[Table] = []
    for t in page.find_tables().tables:
        rows = []
        for row in t.rows:
            cells = [_clean(page.get_textbox(pymupdf.Rect(c))) if c else "" for c in row.cells]
            if any(cells):
                rows.append(cells)
        rows = fold_header_band(rows)
        if len(rows) >= 2:
            out.append(Table(page.number + 1, tuple(t.bbox), rows, page.rect.height))
    out.sort(key=lambda t: t.bbox[1])
    return out


def fold_header_band(rows: list[list[str]]) -> list[list[str]]:
    """Fold a two-row header (spanning group cells over sub-headings) into one header row.

    A band is two rows where the second row starts with an empty cell or the first row has an
    empty cell between filled ones, and the second row holds labels, not numbers. Anything
    else is returned unchanged.
    """
    if len(rows) < 3:
        return rows
    top, sub = rows[0], rows[1]
    filled = [i for i, c in enumerate(top) if c]
    gap_inside = bool(filled) and any(not top[i] for i in range(filled[0], filled[-1] + 1))
    sub_cells = [c for c in sub if c]
    if not sub_cells or not (not sub[0] or gap_inside):
        return rows
    if sum(bool(NUMBER_RE.match(c)) for c in sub_cells) * 2 > len(sub_cells):
        return rows
    folded, group = [], ""  # group: the spanning label currently in force
    for t, u in zip(top, sub):
        if t:
            group = t
        elif not u:
            group = ""  # an empty column ends the span
        label = f"{group} / {u}" if u and group else (u or t)
        folded.append(label)
    return [folded] + rows[2:]


def to_markdown(rows: list[list[str]]) -> str:
    head, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def _norm_header(row: list[str]) -> list[str]:
    return [c.lower() for c in row]


def _continues(a: Table, b: Table, text_below: Callable[[int, float], bool]) -> bool:
    """True when table b, first on the page after a's last part, carries on a.

    Same header and columns, b starts high on its page, and a's last part either ends low on its
    page or is the last thing on it (a table followed by text on its page has ended there).
    """
    last_page, last_box = a.parts[-1]
    ends_page = last_box[3] >= a.page_height * MERGE_BOTTOM_FRAC or not text_below(
        last_page, last_box[3]
    )
    return (
        last_page + 1 == b.page
        and len(a.rows[0]) == len(b.rows[0])
        and _norm_header(a.rows[0]) == _norm_header(b.rows[0])
        and ends_page
        and b.bbox[1] <= b.page_height * MERGE_TOP_FRAC
    )


def merge_continued(
    tables_by_page: dict[int, list[Table]],
    text_below: Callable[[int, float], bool] = lambda page, y: False,
) -> None:
    """Merge a table ending page N with one starting page N+1 when the header row is the same, over any run of pages.

    `text_below(page, y)` says whether a text block that is not part of a table sits below y on that page.
    Mutates tables_by_page: each continuation is folded into the first table and removed.
    """
    tail: Table | None = (
        None  # the table that ends the previous page (the merged one if it spans pages)
    )
    for n in sorted(tables_by_page):
        cur = tables_by_page[n]
        merged = False
        if tail and cur and _continues(tail, cur[0], text_below):
            b = cur.pop(0)
            tail.rows.extend(b.rows[1:])  # identical header repeated on the next page: drop it
            tail.pages = (tail.pages or []) + (b.pages or [b.page])
            tail.parts = (tail.parts or []) + (b.parts or [])
            merged = True
        tail = cur[-1] if cur else (tail if merged else None)
