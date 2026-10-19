"""Polite, cached HTTP fetching shared by every collector.

Rules for every source: a browser User-Agent, at most 4 requests in flight, retries with
backoff, and raw responses cached under ``data/raw/cache/`` so reruns are cheap and resumable.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
CACHE = RAW / "cache"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
MAX_CONCURRENCY = 4
_slots = threading.BoundedSemaphore(MAX_CONCURRENCY)


class Fetcher:
    """Fetch URLs with retries, a shared concurrency limit and an optional disk cache."""

    def __init__(
        self,
        source: str,
        headers: dict[str, str] | None = None,
        retries: int = 4,
        timeout: float = 60,
    ) -> None:
        self.cache_dir = CACHE / source
        self.headers = {"User-Agent": USER_AGENT, **(headers or {})}
        self.retries = retries
        self.timeout = timeout
        self.failures: list[str] = []
        self.network_hits = 0

    def bytes(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        cache: str | None = None,
        refresh: bool = False,
    ) -> bytes | None:
        """Return the body of ``url``, from ``cache`` (a path under the source cache) if present.

        Failed fetches return ``None`` and are recorded in ``self.failures``; they are never
        cached, so a rerun retries them.
        """
        if params:
            url += "?" + urllib.parse.urlencode(params)
        path = self.cache_dir / cache if cache else None
        if path and not refresh and path.exists():
            return path.read_bytes()
        body = self._get(url)
        if body is None:
            self.failures.append(url)
            return None
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(body)
            os.replace(tmp, path)
        return body

    def json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        cache: str | None = None,
        refresh: bool = False,
    ) -> Any:
        body = self.bytes(url, params, cache, refresh)
        if body is None:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            log.warning("not JSON: %s", url)
            if cache:
                (self.cache_dir / cache).unlink(missing_ok=True)
            return None

    def _get(self, url: str) -> bytes | None:
        req = urllib.request.Request(url, headers=self.headers)
        for attempt in range(self.retries):
            try:
                with _slots, urllib.request.urlopen(req, timeout=self.timeout) as r:
                    self.network_hits += 1
                    return r.read()
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    log.warning("404 %s", url)
                    return None
                log.debug("HTTP %s on %s (attempt %d)", e.code, url, attempt + 1)
            except Exception as e:  # network errors, timeouts
                log.debug("%s on %s (attempt %d)", e, url, attempt + 1)
            time.sleep(3 * 2**attempt)
        log.warning("gave up after %d attempts: %s", self.retries, url)
        return None


def pmap[T, R](fn: Callable[[T], R], items: Iterable[T], every: int = 100) -> Iterator[R]:
    """Map ``fn`` over ``items`` on worker threads (the semaphore caps live requests at 4)."""
    items = list(items)
    with cf.ThreadPoolExecutor(MAX_CONCURRENCY) as ex:
        for i, r in enumerate(ex.map(fn, items), 1):
            if i % every == 0 or i == len(items):
                log.info("%d of %d", i, len(items))
            yield r


def write_json(path: Path, data: Any, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
