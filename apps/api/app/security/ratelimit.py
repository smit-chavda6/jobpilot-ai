"""In-process sliding-window rate limiter.

Limitation (documented in ADR-0002): state is per-process. A multi-instance deployment
must swap this for a shared store (e.g. Redis) behind the same `hit()` interface.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from app.errors import RateLimited


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, bucket: str, key: str, limit: int, window_seconds: float) -> None:
        now = time.monotonic()
        k = f"{bucket}:{key}"
        with self._lock:
            q = self._hits[k]
            while q and now - q[0] > window_seconds:
                q.popleft()
            if len(q) >= limit:
                retry = max(1, int(window_seconds - (now - q[0])))
                raise RateLimited("Too many requests, please slow down", details={"retry_after_seconds": retry})
            q.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()

# (limit, window seconds) per bucket.
LIMITS: dict[str, tuple[int, float]] = {
    "ip_global": (600, 60),
    "auth": (20, 60),
    "ai": (30, 60),
    "import": (60, 60),
    "upload": (20, 60),
}


def enforce(bucket: str, key: str) -> None:
    limit, window = LIMITS[bucket]
    limiter.hit(bucket, key, limit, window)
