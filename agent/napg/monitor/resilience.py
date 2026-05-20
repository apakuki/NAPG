"""Per-provider rate-limiting and circuit-breaking for RPC calls.

Two small primitives:

- `RateLimiter` is a token bucket. The heartbeat calls `acquire()` before every
  RPC round trip. If the bucket is empty, it sleeps for the time it would take
  the bucket to refill one token. Default rate of 5 req/s with a burst of 5 is
  comfortably under what Alchemy and QuickNode allow on their lowest paid tier;
  tune via env if a provider is tighter.

- `CircuitBreaker` flips open after `failure_threshold` consecutive failures
  and rejects calls for `cooldown_s` afterwards. After the cooldown, the next
  call is allowed (half-open); success closes the breaker, failure re-opens it.

`FailoverRpcHeartbeat` wires several `RpcHeartbeat` instances behind one
`tick()` call. Each provider carries its own limiter + breaker, so a flaky
provider can be cut over without affecting the healthy one. The first provider
whose breaker isn't open gets the call; if it raises, the breaker records the
failure and the next provider is tried. The active provider is sticky so we
don't re-introduce reorg false positives from cross-provider hash diffs.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import Literal, TypeVar

from napg.monitor.rpc import HeartbeatResult, RpcHeartbeat

T = TypeVar("T")


class CircuitOpen(RuntimeError):
    """Raised by `CircuitBreaker.before_call` when the breaker is open."""


class RateLimiter:
    """Token-bucket limiter. `acquire()` blocks until one token is available."""

    def __init__(
        self,
        rate_per_sec: float,
        capacity: int,
        *,
        now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be > 0")
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self._rate = float(rate_per_sec)
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._last = now()
        self._now = now
        self._sleep = sleep

    @property
    def tokens(self) -> float:
        self._refill()
        return self._tokens

    def acquire(self) -> None:
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return
        wait = (1.0 - self._tokens) / self._rate
        self._sleep(wait)
        self._refill()
        self._tokens = max(0.0, self._tokens - 1.0)

    def _refill(self) -> None:
        now = self._now()
        elapsed = max(0.0, now - self._last)
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last = now


CircuitState = Literal["closed", "open", "half_open"]


class CircuitBreaker:
    """Trip open after consecutive failures; recover after a cooldown window."""

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_s: float = 30.0,
        *,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if cooldown_s <= 0:
            raise ValueError("cooldown_s must be > 0")
        self._threshold = failure_threshold
        self._cooldown = float(cooldown_s)
        self._now = now
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        if self._opened_at is None:
            return "closed"
        if self._now() - self._opened_at >= self._cooldown:
            return "half_open"
        return "open"

    @property
    def consecutive_failures(self) -> int:
        return self._failures

    def before_call(self) -> None:
        if self.state == "open":
            raise CircuitOpen("circuit breaker is open")

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = self._now()


def gated_call(
    fn: Callable[[], T],
    *,
    limiter: RateLimiter | None = None,
    breaker: CircuitBreaker | None = None,
) -> T:
    """Run `fn` through an optional limiter + breaker.

    The same shape that `FailoverRpcHeartbeat` uses per-provider, exposed as a
    standalone helper so monitors that don't fit the failover model (Morpho's
    single-RPC poll, Aerodrome's single 0x endpoint) can still gate their
    outbound calls. Order: breaker first (fail-fast if open), then limiter
    (cap throughput), then the call; success/failure records on the breaker.
    """
    if breaker is not None:
        breaker.before_call()
    if limiter is not None:
        limiter.acquire()
    try:
        result = fn()
    except Exception:
        if breaker is not None:
            breaker.record_failure()
        raise
    if breaker is not None:
        breaker.record_success()
    return result


class _Provider:
    """One heartbeat + its limiter + its breaker."""

    __slots__ = ("breaker", "heart", "label", "limiter")

    def __init__(
        self,
        heart: RpcHeartbeat,
        limiter: RateLimiter | None,
        breaker: CircuitBreaker | None,
        label: str,
    ) -> None:
        self.heart = heart
        self.limiter = limiter
        self.breaker = breaker
        self.label = label


class FailoverRpcHeartbeat:
    """Try each provider in order; cut over when a breaker opens or a call raises.

    State is intentionally minimal: which provider served the last tick. A
    consecutive tick from the same provider keeps the reorg-detection history
    in `RpcHeartbeat._history` aligned, so the failover path doesn't introduce
    spurious reorg signals from cross-provider hash drift.
    """

    def __init__(
        self,
        providers: Iterable[RpcHeartbeat],
        *,
        rate_per_sec: float = 5.0,
        burst: int = 5,
        failure_threshold: int = 3,
        cooldown_s: float = 30.0,
        limiter_factory: Callable[[], RateLimiter] | None = None,
        breaker_factory: Callable[[], CircuitBreaker] | None = None,
    ) -> None:
        provider_list = list(providers)
        if not provider_list:
            raise ValueError("FailoverRpcHeartbeat requires at least one provider")

        def _default_limiter() -> RateLimiter:
            return RateLimiter(rate_per_sec=rate_per_sec, capacity=burst)

        def _default_breaker() -> CircuitBreaker:
            return CircuitBreaker(failure_threshold=failure_threshold, cooldown_s=cooldown_s)

        mk_limiter = limiter_factory or _default_limiter
        mk_breaker = breaker_factory or _default_breaker
        self._providers: list[_Provider] = [
            _Provider(heart, mk_limiter(), mk_breaker(), heart.rpc_url) for heart in provider_list
        ]
        self._active_index = 0

    @property
    def active_label(self) -> str:
        return self._providers[self._active_index].label

    def tick(self) -> HeartbeatResult:
        errors: list[tuple[str, Exception]] = []
        for index in self._order():
            provider = self._providers[index]
            if provider.breaker is not None:
                try:
                    provider.breaker.before_call()
                except CircuitOpen as exc:
                    errors.append((provider.label, exc))
                    continue
            if provider.limiter is not None:
                provider.limiter.acquire()
            try:
                result = provider.heart.tick()
            except Exception as exc:
                if provider.breaker is not None:
                    provider.breaker.record_failure()
                errors.append((provider.label, exc))
                continue
            if provider.breaker is not None:
                provider.breaker.record_success()
            self._active_index = index
            return result
        raise RuntimeError(
            "all RPC providers failed: "
            + ", ".join(f"{label}: {type(err).__name__}" for label, err in errors)
        )

    def _order(self) -> list[int]:
        """Return provider indexes to try: active first, then the rest in order."""
        rest = [i for i in range(len(self._providers)) if i != self._active_index]
        return [self._active_index, *rest]


__all__ = [
    "CircuitBreaker",
    "CircuitOpen",
    "FailoverRpcHeartbeat",
    "RateLimiter",
    "gated_call",
]
