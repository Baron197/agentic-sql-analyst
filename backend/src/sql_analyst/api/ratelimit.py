"""Per-user rate limits (sliding window, in memory).

One API process keeps the counts in memory, which is right for a single container (the
deployment target). Several instances would each count separately; they would need the
counts in Postgres or Redis instead (docs/DECISIONS.md D032).
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


class SlidingWindowLimiter:
    def __init__(
        self, limit: int, window_s: float = 60.0, clock: Callable[[], float] = time.monotonic
    ):
        self.limit, self.window_s, self.clock = limit, window_s, clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window_s:
            hits.popleft()
        return hits

    def allow(self, key: str) -> bool:
        """Count one hit for `key` if it is under the limit; False (not counted) otherwise."""
        with self._lock:
            now = self.clock()
            hits = self._prune(key, now)
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def blocked(self, key: str) -> bool:
        """True if `key` is at the limit (does not count a hit)."""
        with self._lock:
            return len(self._prune(key, self.clock())) >= self.limit

    def hit(self, key: str) -> None:
        with self._lock:
            now = self.clock()
            self._prune(key, now).append(now)

    def retry_after_s(self, key: str) -> int:
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return 0
            return max(1, int(self.window_s - (self.clock() - hits[0])) + 1)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
