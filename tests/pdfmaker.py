"""Build small synthetic PDFs with PyMuPDF for ingestion tests."""

import pymupdf

FOOTER = "Acme Corp Annual Report  Page {n}"


def draw_table(
    page: pymupdf.Page, x: float, y: float, rows: list[list[str]], w: float = 90, h: float = 20
) -> float:
    """Draw a ruled table at (x, y); returns the bottom y."""
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            rect = pymupdf.Rect(x + c * w, y + r * h, x + (c + 1) * w, y + (r + 1) * h)
            page.draw_rect(rect, color=(0, 0, 0), width=0.8)
            page.insert_text((rect.x0 + 4, rect.y1 - 6), text, fontsize=9)
    return y + len(rows) * h


def build_pdf(path, pages: list[dict]) -> None:
    """pages: [{"text": [(y, str, size)], "table": (y, rows), "image": (x0,y0,x1,y1)}, ...]"""
    doc = pymupdf.open()
    for n, spec in enumerate(pages, 1):
        page = doc.new_page(width=595, height=842)
        for y, text, size in spec.get("text", []):
            page.insert_text((57, y), text, fontsize=size)
        if "table" in spec:
            y, rows = spec["table"]
            draw_table(page, 57, y, rows)
        if "image" in spec:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 60), False)
            pix.clear_with(200)
            page.insert_image(pymupdf.Rect(*spec["image"]), pixmap=pix, keep_proportion=False)
        page.insert_text((57, 820), FOOTER.format(n=n), fontsize=8)
    doc.save(path)


def text_box(
    page: pymupdf.Page, x0: float, y0: float, x1: float, text: str, size: float = 10
) -> float:
    """One paragraph as its own block, wrapped to the given width; returns the bottom y."""
    rect = pymupdf.Rect(x0, y0, x1, y0 + 400)
    page.insert_textbox(rect, text, fontsize=size)
    block = page.get_text("blocks", clip=rect)[-1]
    return block[3]


def build_layout_pdf(path, pages: list[list[tuple]]) -> None:
    """pages: [[(x0, y0, x1, text, size), ...], ...]; every item is a separate text block."""
    doc = pymupdf.open()
    for n, items in enumerate(pages, 1):
        page = doc.new_page(width=595, height=842)
        for x0, y0, x1, text, size in items:
            text_box(page, x0, y0, x1, text, size)
        page.insert_text((57, 820), FOOTER.format(n=n), fontsize=8)
    doc.save(path)
