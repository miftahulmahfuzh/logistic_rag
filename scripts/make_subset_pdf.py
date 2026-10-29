"""Build a smaller PDF from selected pages of another PDF (generality proof).

Usage: python scripts/make_subset_pdf.py <source.pdf> <out.pdf> 7-9,13
"""

import sys

import pymupdf


def parse_pages(spec: str) -> list[int]:
    """'7-9,13' -> [7, 8, 9, 13] (1-based)."""
    pages: list[int] = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        pages += range(int(lo), int(hi or lo) + 1)
    return pages


def main(src: str, dst: str, spec: str) -> None:
    out = pymupdf.open()
    with pymupdf.open(src) as doc:
        for p in parse_pages(spec):
            out.insert_pdf(doc, from_page=p - 1, to_page=p - 1)
    out.save(dst)
    print(f"wrote {dst} ({out.page_count} pages from {src}: {spec})")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
