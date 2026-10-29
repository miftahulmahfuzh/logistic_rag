"""Image regions (charts, KPI cards, diagrams, scans): selection, crops, VLM transcription."""

from dataclasses import dataclass

import pymupdf

from .. import config, llm
from .pdf import CAPTION_RE, Block, PageRecord

VISION_PROMPT = (
    "Transcribe this image from a document. Begin with its title, heading or caption line if it has one. Then transcribe every visible title, axis label, legend "
    "entry, data label, table cell and annotation exactly as printed. "
    "For charts, give a markdown table of series -> value (one row per category or point). "
    "For diagrams, list each node and each labelled edge as `A -- label --> B`. "
    "For scanned pages, transcribe the full text and any table. "
    "Do not estimate values that are not printed. If something is unreadable write [unreadable]. "
    "Output markdown only."
)
SCAN_FRAC = 0.6  # an image this large, or any image on a text-less page, is a scanned page


@dataclass
class ImageRegion:
    bbox: tuple[float, float, float, float]
    page_frac: float
    kind: str  # "figure" | "scan"


def _area(r: tuple[float, float, float, float]) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _contained(inner: tuple, outer: tuple, frac: float = 0.9) -> bool:
    ix0, iy0 = max(inner[0], outer[0]), max(inner[1], outer[1])
    ix1, iy1 = min(inner[2], outer[2]), min(inner[3], outer[3])
    return _area((ix0, iy0, ix1, iy1)) >= frac * _area(inner)


def select_regions(page: pymupdf.Page, text_chars: int) -> list[ImageRegion]:
    """Embedded images worth sending to the VLM: >= 3% of the page, or any image on a text-less page."""
    page_area = page.rect.width * page.rect.height
    infos = sorted((tuple(i["bbox"]) for i in page.get_image_info()), key=_area, reverse=True)
    textless = text_chars < config.VISION_MIN_TEXT_CHARS
    chosen: list[tuple] = []
    for bbox in infos:
        frac = _area(bbox) / page_area
        if frac < config.VISION_MIN_AREA_FRAC and not textless:
            continue
        if any(_contained(bbox, c) for c in chosen):
            continue
        chosen.append(bbox)
    chosen.sort(key=lambda b: (b[1], b[0]))
    return [
        ImageRegion(
            b,
            _area(b) / page_area,
            "scan" if textless or _area(b) / page_area >= SCAN_FRAC else "figure",
        )
        for b in chosen
    ]


def render_crop(page: pymupdf.Page, bbox: tuple, pad: float = 4.0) -> bytes:
    """Render the region at the configured DPI as PNG bytes."""
    clip = pymupdf.Rect(bbox) + (-pad, -pad, pad, pad)
    clip &= page.rect
    return page.get_pixmap(dpi=config.VISION_DPI, clip=clip).tobytes("png")


def transcribe(png: bytes) -> llm.LLMResult:
    return llm.describe_image(png, VISION_PROMPT)


def find_caption(
    blocks: list[Block], bbox: tuple, table: bool = False, max_gap: float = 70.0
) -> Block | None:
    """Nearest caption block just above or below a region: `Table N` for tables, else the rest."""
    best, best_gap = None, max_gap
    for b in blocks:
        m = CAPTION_RE.match(b.text)
        if not m or (m.group(1).lower() == "table") != table:
            continue
        if b.bbox[3] <= bbox[1] + 2:  # caption above
            gap = bbox[1] - b.bbox[3]
        elif b.bbox[1] >= bbox[3] - 2:  # caption below
            gap = b.bbox[1] - bbox[3]
        else:
            continue
        if gap < best_gap:
            best, best_gap = b, gap
    return best


def blocks_inside(page: PageRecord, bbox: tuple) -> list[Block]:
    """Text blocks whose centre lies inside the region (they belong to the image, not to prose)."""
    return [b for b in page.blocks if _centre_inside(b.bbox, bbox)]


def _centre_inside(inner: tuple, outer: tuple) -> bool:
    cx, cy = (inner[0] + inner[2]) / 2, (inner[1] + inner[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]
