from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import monotonic


@dataclass(slots=True)
class _Bucket:
    events: deque[float]


class SlidingWindowRateLimiter:
    """Small bounded limiter for Telegram ingress; it has no model-facing state."""

    def __init__(
        self,
        *,
        max_events: int = 30,
        window_seconds: float = 60.0,
        max_subjects: int = 10_000,
    ) -> None:
        if max_events <= 0 or window_seconds <= 0 or max_subjects <= 0:
            raise ValueError("rate limiter settings must be positive")
        self._max_events = max_events
        self._window_seconds = window_seconds
        self._max_subjects = max_subjects
        self._buckets: dict[int, _Bucket] = {}

    def allow(self, subject_id: int, *, now: float | None = None) -> bool:
        current = monotonic() if now is None else now
        bucket = self._buckets.get(subject_id)
        if bucket is None:
            if len(self._buckets) >= self._max_subjects:
                self._evict_oldest_bucket()
            bucket = _Bucket(events=deque())
            self._buckets[subject_id] = bucket

        cutoff = current - self._window_seconds
        while bucket.events and bucket.events[0] <= cutoff:
            bucket.events.popleft()
        if len(bucket.events) >= self._max_events:
            return False
        bucket.events.append(current)
        return True

    def _evict_oldest_bucket(self) -> None:
        if not self._buckets:
            return
        oldest_subject = min(
            self._buckets,
            key=lambda subject: self._buckets[subject].events[-1]
            if self._buckets[subject].events
            else float("-inf"),
        )
        del self._buckets[oldest_subject]
