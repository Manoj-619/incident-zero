from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    per_minute: int = 10
    _hits: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def allow(self, key: str) -> bool:
        now = time.time()
        window = self._hits[key]
        self._hits[key] = [t for t in window if now - t < 60]
        if len(self._hits[key]) >= self.per_minute:
            return False
        self._hits[key].append(now)
        return True


@dataclass
class DailyCap:
    cap: int = 5
    _counts: dict[str, tuple[str, int]] = field(default_factory=dict)

    def _day_key(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    def allow(self, key: str) -> bool:
        day = self._day_key()
        prev = self._counts.get(key)
        if prev is None or prev[0] != day:
            self._counts[key] = (day, 1)
            return True
        if prev[1] >= self.cap:
            return False
        self._counts[key] = (day, prev[1] + 1)
        return True
