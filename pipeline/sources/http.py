"""Shared HTTP plumbing: retries, throttling and an on-disk cache.

Both upstream sources are public services run on someone else's budget, so
every request made here is cached, rate-limited and identified. The cache also
makes the pipeline cheap to re-run while developing a parser.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

USER_AGENT = os.environ.get(
    "ORELYSIS_UA",
    "orelysis-critical-minerals/1.0 (open-data hobby project; "
    "https://github.com/{owner}/{repo})",
)

CACHE_DIR = Path(
    os.environ.get("ORELYSIS_CACHE_DIR", Path(__file__).resolve().parents[2] / ".cache")
)
CACHE_TTL_SECONDS = int(os.environ.get("NINE_CACHE_TTL", 60 * 60 * 24))

_last_request_at: dict[str, float] = {}
MIN_INTERVAL_SECONDS = float(os.environ.get("NINE_MIN_INTERVAL", "1.0"))


class FetchError(RuntimeError):
    """A request failed in a way the caller is expected to report, not retry."""


def _cache_path(url: str, params: dict | None, suffix: str) -> Path:
    key = hashlib.sha256(
        (url + json.dumps(params or {}, sort_keys=True)).encode("utf-8")
    ).hexdigest()[:32]
    return CACHE_DIR / f"{key}{suffix}"


def _throttle(url: str) -> None:
    host = url.split("/")[2] if "://" in url else url
    last = _last_request_at.get(host)
    if last is not None:
        wait = MIN_INTERVAL_SECONDS - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
    _last_request_at[host] = time.time()


def get(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = 60,
    retries: int = 3,
    binary: bool = False,
    use_cache: bool = True,
) -> bytes:
    """GET with retry, throttle and cache. Returns raw bytes."""
    path = _cache_path(url, params, ".bin" if binary else ".txt")
    if use_cache and path.exists():
        age = time.time() - path.stat().st_mtime
        if age < CACHE_TTL_SECONDS:
            log.debug("cache hit %s (%ds old)", url, int(age))
            return path.read_bytes()

    all_headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    all_headers.update(headers or {})

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        _throttle(url)
        try:
            response = requests.get(
                url, params=params, headers=all_headers, timeout=timeout
            )
        except requests.RequestException as exc:  # network-level
            last_error = exc
            log.warning("attempt %d/%d failed for %s: %s", attempt, retries, url, exc)
            time.sleep(min(2**attempt, 20))
            continue

        if response.status_code == 429 or 500 <= response.status_code < 600:
            last_error = FetchError(f"HTTP {response.status_code} from {url}")
            retry_after = response.headers.get("Retry-After")
            delay = (
                float(retry_after)
                if retry_after and retry_after.isdigit()
                else min(2**attempt, 30)
            )
            log.warning(
                "attempt %d/%d got HTTP %d for %s; sleeping %.0fs",
                attempt,
                retries,
                response.status_code,
                url,
                delay,
            )
            time.sleep(delay)
            continue

        if not response.ok:
            # 4xx other than 429 will not fix itself; surface it immediately.
            raise FetchError(
                f"HTTP {response.status_code} from {url}: {response.text[:300]}"
            )

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return response.content

    raise FetchError(f"giving up on {url} after {retries} attempts: {last_error}")


def get_json(url: str, **kwargs) -> dict:
    raw = get(url, **kwargs)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FetchError(f"{url} did not return JSON: {raw[:200]!r}") from exc
