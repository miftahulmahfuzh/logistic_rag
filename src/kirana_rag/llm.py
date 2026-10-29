"""Text and vision LLM clients with retry, concurrency limit, disk cache and usage accounting."""

import base64
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field

import httpx

from . import config

_SEM = threading.BoundedSemaphore(config.MAX_CONCURRENCY)
_RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 6


@dataclass
class LLMResult:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    cached: bool = False


@dataclass
class Usage:
    """Running token totals for a session (cached calls count as zero tokens)."""

    calls: int = 0
    cached_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    by_model: dict[str, list[int]] = field(default_factory=dict)

    def add(self, model: str, res: LLMResult) -> None:
        self.calls += 1
        if res.cached:
            self.cached_calls += 1
            return
        self.tokens_in += res.tokens_in
        self.tokens_out += res.tokens_out
        m = self.by_model.setdefault(model, [0, 0])
        m[0] += res.tokens_in
        m[1] += res.tokens_out


USAGE = Usage()

# Mixed into the text-call cache key when non-empty. A repeated eval run sets a different salt per
# repeat, so answer and judge calls are fresh while vision calls (no salt) keep hitting the cache.
CACHE_SALT = ""


def _cache_key(*parts: str | bytes) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else p.encode())
        h.update(b"\x00")
    return h.hexdigest()


def _cache_get(key: str) -> LLMResult | None:
    path = config.LLM_CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return LLMResult(**{**data, "cached": True})


def _cache_put(key: str, res: LLMResult) -> None:
    config.LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.LLM_CACHE_DIR / f"{key}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({**res.__dict__, "cached": False}))
    tmp.replace(path)


def _post(url: str, headers: dict, payload: dict) -> dict:
    """POST with exponential backoff on 429/5xx. Never logs headers (they hold the key)."""
    delay = 2.0
    for attempt in range(MAX_RETRIES + 1):
        with _SEM:
            try:
                r = httpx.post(url, headers=headers, json=payload, timeout=180)
            except httpx.TransportError:
                r = None
        if r is not None and r.status_code == 200:
            return r.json()
        retryable = r is None or r.status_code in _RETRY_STATUS
        if not retryable or attempt == MAX_RETRIES:
            code = "network error" if r is None else f"HTTP {r.status_code}: {r.text[:300]}"
            raise RuntimeError(f"LLM request failed ({code})")
        time.sleep(delay)
        delay = min(delay * 2, 60)
    raise RuntimeError("unreachable")


def complete(
    prompt: str,
    system: str = "",
    max_tokens: int = 800,
    temperature: float = 0.0,
    use_cache: bool = True,
) -> LLMResult:
    """Text completion via the Anthropic Messages API, thinking disabled."""
    s = config.settings()
    parts = ["text", s.model, system, prompt, str(max_tokens), str(temperature)]
    key = _cache_key(*parts, CACHE_SALT) if CACHE_SALT else _cache_key(*parts)
    if use_cache and (hit := _cache_get(key)):
        USAGE.add(s.model, hit)
        return hit
    payload = {
        "model": s.model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    headers = {
        "x-api-key": s.api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    t0 = time.perf_counter()
    data = _post(f"{s.base_url}/v1/messages", headers, payload)
    ms = (time.perf_counter() - t0) * 1000
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    usage = data.get("usage", {})
    res = LLMResult(text, usage.get("input_tokens", 0), usage.get("output_tokens", 0), ms)
    _cache_put(key, res)
    USAGE.add(s.model, res)
    return res


def describe_image(
    png: bytes, prompt: str, max_tokens: int = 4000, use_cache: bool = True
) -> LLMResult:
    """Vision call via the OpenAI-style chat completions API."""
    s = config.settings()
    key = _cache_key("vision", s.vision_model, prompt, png)
    if use_cache and (hit := _cache_get(key)):
        USAGE.add(s.vision_model, hit)
        return hit
    b64 = base64.b64encode(png).decode()
    payload = {
        "model": s.vision_model,
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }
        ],
    }
    headers = {"Authorization": f"Bearer {s.api_key}", "content-type": "application/json"}
    t0 = time.perf_counter()
    data = _post(f"{s.vision_base_url}/chat/completions", headers, payload)
    ms = (time.perf_counter() - t0) * 1000
    msg = data["choices"][0]["message"]
    usage = data.get("usage", {})
    res = LLMResult(
        msg.get("content") or "",
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
        ms,
    )
    _cache_put(key, res)
    USAGE.add(s.vision_model, res)
    return res
