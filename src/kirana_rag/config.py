"""Environment loading, paths and tunable constants. Secrets are read here and nowhere else."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env.local")

CACHE_DIR = Path(os.environ.get("KIRANA_CACHE_DIR", ROOT / ".cache"))
LLM_CACHE_DIR = CACHE_DIR / "llm"
EVAL_DIR = ROOT / "eval"

DEFAULT_TOP_K = 5
MAX_CONCURRENCY = 2
VISION_DPI = 200
VISION_MIN_AREA_FRAC = 0.03
VISION_MIN_TEXT_CHARS = 150

# USD per million tokens (input, output), z.ai pay-as-you-go list prices (docs.z.ai/guides/overview/pricing,
# read 2026-10-29). The author actually pays a flat subscription, so this is a "what would it cost at list
# price" figure. Cached-input discounts are ignored. Unknown models are reported as "unknown".
PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "glm-5.3": (1.4, 4.4),
    "glm-4.6v": (0.3, 0.9),
}


@dataclass(frozen=True)
class LLMSettings:
    api_key: str
    base_url: str
    model: str
    vision_base_url: str
    vision_model: str


def settings() -> LLMSettings:
    """Read LLM settings from the environment (loaded from .env.local)."""
    return LLMSettings(
        api_key=os.environ.get("LLM_API_KEY", ""),
        base_url=os.environ.get("LLM_BASE_URL", "https://api.z.ai/api/anthropic").rstrip("/"),
        model=os.environ.get("LLM_MODEL", "glm-5.3"),
        vision_base_url=os.environ.get(
            "VISION_BASE_URL", "https://api.z.ai/api/coding/paas/v4"
        ).rstrip("/"),
        vision_model=os.environ.get("VISION_MODEL", "glm-4.6v"),
    )


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float | None:
    """Estimated USD cost, or None when no price is configured for the model."""
    price = PRICE_PER_MTOK.get(model)
    if price is None:
        return None
    return (tokens_in * price[0] + tokens_out * price[1]) / 1_000_000
