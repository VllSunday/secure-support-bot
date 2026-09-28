from __future__ import annotations

from secure_support_bot.security.rate_limit import SlidingWindowRateLimiter


def test_rate_limiter_blocks_after_window_budget() -> None:
    limiter = SlidingWindowRateLimiter(max_events=2, window_seconds=10)

    assert limiter.allow(10, now=100.0)
    assert limiter.allow(10, now=101.0)
    assert not limiter.allow(10, now=102.0)
    assert limiter.allow(10, now=111.0)


def test_rate_limiter_evicts_subjects_with_bounded_memory() -> None:
    limiter = SlidingWindowRateLimiter(max_events=1, max_subjects=2)

    assert limiter.allow(1, now=1.0)
    assert limiter.allow(2, now=2.0)
    assert limiter.allow(3, now=3.0)
    assert len(limiter._buckets) == 2  # noqa: SLF001 - bounded-state invariant
