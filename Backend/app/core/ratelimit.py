"""Per-IP throttling for the endpoints that attackers hammer.

Counters live in this process, so running uvicorn with --workers N multiplies
every limit by N. That is fine for one backend; move the counters to Postgres
before you scale out.
"""

import threading
import time
from collections import deque

from fastapi import HTTPException, Request

from app.core.config import settings

MAX_KEYS = 100_000


def client_ip(request: Request) -> str:
    if settings.trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip() or "unknown"
    return request.client.host if request.client else "unknown"


class SlidingWindow:
    def __init__(self, name: str, allowed: int, window_seconds: int):
        self.name = name
        self.allowed = allowed
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _retry_after(self, key: str, now: float) -> int:
        hits = self._hits.get(key)
        if not hits:
            return 1
        wait = hits[0] + self.window_seconds - now
        return max(1, int(wait) + 1)

    def hit(self, key: str) -> int:
        """Consume one request. Returns 0 when allowed, else seconds to wait."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= MAX_KEYS:
                    self._sweep(now)
                    # One IP can only create one key, so a full table after a
                    # sweep means abuse. Refuse new IPs until keys expire.
                    if len(self._hits) >= MAX_KEYS:
                        return self.window_seconds
                hits = self._hits[key] = deque()
            cutoff = now - self.window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.allowed:
                return self._retry_after(key, now)
            hits.append(now)
            return 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def _sweep(self, now: float) -> None:
        cutoff = now - self.window_seconds
        for key, hits in list(self._hits.items()):
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if not hits:
                del self._hits[key]


auth_login = SlidingWindow("auth login", 10, 5 * 60)
auth_register = SlidingWindow("auth register", 5, 60 * 60)
auth_refresh = SlidingWindow("auth refresh", 60, 10 * 60)
admin_login = SlidingWindow("admin login", 5, 10 * 60)
admin_upload = SlidingWindow("admin upload", 30, 60 * 60)
# A reader flipping pages in a 300-page PDF hits this route for every page.
page_view = SlidingWindow("page view", 600, 5 * 60)


def limit(window: SlidingWindow):
    def dependency(request: Request) -> None:
        wait = window.hit(client_ip(request))
        if wait:
            raise HTTPException(
                429,
                "Too many requests from this IP. Try again later.",
                headers={"Retry-After": str(wait)},
            )

    return dependency
