"""Unit tests for napg.monitor.resilience — rate-limiter, breaker, failover heartbeat."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from napg.monitor.resilience import (
    CircuitBreaker,
    CircuitOpen,
    FailoverRpcHeartbeat,
    RateLimiter,
    gated_call,
)
from napg.monitor.rpc import RpcHeartbeat


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


HASH_A = "0x" + "aa" * 32
HASH_B = "0x" + "bb" * 32


def _block(number: int, hash_hex: str, parent_hex: str, ts: int = 1_700_000_000) -> dict[str, Any]:
    return {
        "number": number,
        "hash": bytes.fromhex(hash_hex[2:]),
        "parentHash": bytes.fromhex(parent_hex[2:]),
        "timestamp": ts,
    }


def _make_web3(chain_id: int, blocks: list[dict[str, Any]]) -> MagicMock:
    web3 = MagicMock()
    web3.eth.chain_id = chain_id
    iterator = iter(blocks)
    web3.eth.get_block.side_effect = lambda _identifier: next(iterator)
    return web3


def _failing_web3(chain_id: int = 84532) -> MagicMock:
    web3 = MagicMock()
    web3.eth.chain_id = chain_id
    web3.eth.get_block.side_effect = RuntimeError("provider down")
    return web3


def _new_heart(url: str, web3: Any) -> RpcHeartbeat:
    return RpcHeartbeat(url, web3=web3)


# --- RateLimiter ---------------------------------------------------------------


def test_rate_limiter_rejects_invalid_arguments():
    with pytest.raises(ValueError, match="rate_per_sec"):
        RateLimiter(rate_per_sec=0, capacity=1)
    with pytest.raises(ValueError, match="capacity"):
        RateLimiter(rate_per_sec=1, capacity=0)


def test_rate_limiter_lets_through_a_burst_without_sleeping():
    clock = _FakeClock()
    limiter = RateLimiter(rate_per_sec=5, capacity=5, now=clock.time, sleep=clock.sleep)

    for _ in range(5):
        limiter.acquire()

    assert clock.sleeps == []


def test_rate_limiter_sleeps_when_bucket_drained():
    clock = _FakeClock()
    limiter = RateLimiter(rate_per_sec=5, capacity=1, now=clock.time, sleep=clock.sleep)

    limiter.acquire()  # consume the single starting token
    limiter.acquire()  # forces a sleep

    assert clock.sleeps == [pytest.approx(0.2)]


def test_rate_limiter_refills_with_elapsed_time():
    clock = _FakeClock()
    limiter = RateLimiter(rate_per_sec=10, capacity=1, now=clock.time, sleep=clock.sleep)

    limiter.acquire()
    clock.advance(0.5)  # plenty of time to refill the one-token bucket
    limiter.acquire()

    assert clock.sleeps == []


def test_rate_limiter_caps_tokens_at_capacity():
    clock = _FakeClock()
    limiter = RateLimiter(rate_per_sec=10, capacity=2, now=clock.time, sleep=clock.sleep)

    clock.advance(60)  # enough time for hundreds of tokens to refill
    assert limiter.tokens == pytest.approx(2.0)


# --- CircuitBreaker ------------------------------------------------------------


def test_circuit_breaker_rejects_invalid_arguments():
    with pytest.raises(ValueError, match="failure_threshold"):
        CircuitBreaker(failure_threshold=0)
    with pytest.raises(ValueError, match="cooldown_s"):
        CircuitBreaker(failure_threshold=1, cooldown_s=0)


def test_circuit_breaker_starts_closed_and_passes_calls_through():
    clock = _FakeClock()
    breaker = CircuitBreaker(failure_threshold=3, cooldown_s=10, now=clock.time)

    assert breaker.state == "closed"
    breaker.before_call()  # no raise


def test_circuit_breaker_trips_after_consecutive_failures():
    clock = _FakeClock()
    breaker = CircuitBreaker(failure_threshold=3, cooldown_s=10, now=clock.time)

    for _ in range(2):
        breaker.record_failure()
    assert breaker.state == "closed"

    breaker.record_failure()
    assert breaker.state == "open"
    with pytest.raises(CircuitOpen):
        breaker.before_call()


def test_circuit_breaker_success_resets_failure_count():
    clock = _FakeClock()
    breaker = CircuitBreaker(failure_threshold=3, cooldown_s=10, now=clock.time)

    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    breaker.record_failure()

    assert breaker.state == "closed"


def test_circuit_breaker_half_opens_after_cooldown_and_closes_on_success():
    clock = _FakeClock()
    breaker = CircuitBreaker(failure_threshold=2, cooldown_s=5, now=clock.time)

    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == "open"

    clock.advance(5.0)
    assert breaker.state == "half_open"
    breaker.before_call()  # half-open allows the probe call

    breaker.record_success()
    assert breaker.state == "closed"


def test_circuit_breaker_reopens_if_half_open_call_fails():
    clock = _FakeClock()
    breaker = CircuitBreaker(failure_threshold=2, cooldown_s=5, now=clock.time)

    breaker.record_failure()
    breaker.record_failure()
    clock.advance(5.0)

    breaker.record_failure()  # half-open probe fails
    assert breaker.state == "open"


# --- FailoverRpcHeartbeat ------------------------------------------------------


def test_failover_requires_at_least_one_provider():
    with pytest.raises(ValueError, match="at least one"):
        FailoverRpcHeartbeat([])


def test_failover_uses_primary_when_healthy():
    primary_web3 = _make_web3(84532, [_block(100, HASH_A, HASH_B)])
    fallback_web3 = _make_web3(84532, [_block(999, HASH_A, HASH_B)])

    primary = _new_heart("https://primary.example/rpc", primary_web3)
    fallback = _new_heart("https://fallback.example/rpc", fallback_web3)
    pool = FailoverRpcHeartbeat([primary, fallback])

    result = pool.tick()

    assert result.block.number == 100
    assert pool.active_label == "https://primary.example/rpc"
    fallback_web3.eth.get_block.assert_not_called()


def test_failover_cuts_over_after_breaker_trips():
    primary_web3 = _failing_web3()
    fallback_web3 = _make_web3(84532, [_block(200, HASH_A, HASH_B)])

    primary = _new_heart("https://primary.example/rpc", primary_web3)
    fallback = _new_heart("https://fallback.example/rpc", fallback_web3)
    pool = FailoverRpcHeartbeat(
        [primary, fallback],
        rate_per_sec=1000,  # rate-limit isn't what we're testing
        burst=1000,
        failure_threshold=1,
        cooldown_s=60,
    )

    result = pool.tick()

    assert result.block.number == 200
    assert pool.active_label == "https://fallback.example/rpc"


def test_failover_sticks_to_fallback_until_primary_recovers():
    primary_web3 = _failing_web3()
    fallback_web3 = _make_web3(
        84532,
        [
            _block(200, HASH_A, HASH_B),
            _block(201, HASH_A, HASH_B),  # second tick from fallback chains arbitrarily
        ],
    )

    primary = _new_heart("https://primary.example/rpc", primary_web3)
    fallback = _new_heart("https://fallback.example/rpc", fallback_web3)
    pool = FailoverRpcHeartbeat(
        [primary, fallback],
        rate_per_sec=1000,
        burst=1000,
        failure_threshold=1,
        cooldown_s=60,
    )

    pool.tick()
    pool.tick()

    # Primary breaker is open, so primary was never re-tried on the second tick.
    assert primary_web3.eth.get_block.call_count == 1
    assert fallback_web3.eth.get_block.call_count == 2


def test_failover_raises_when_all_providers_fail():
    primary = _new_heart("https://primary.example/rpc", _failing_web3())
    fallback = _new_heart("https://fallback.example/rpc", _failing_web3())
    pool = FailoverRpcHeartbeat(
        [primary, fallback],
        rate_per_sec=1000,
        burst=1000,
        failure_threshold=1,
        cooldown_s=60,
    )

    with pytest.raises(RuntimeError, match="all RPC providers failed"):
        pool.tick()


def test_gated_call_with_no_limiter_or_breaker_just_runs_fn():
    result = gated_call(lambda: 42)
    assert result == 42


def test_gated_call_invokes_limiter_acquire_before_fn():
    clock = _FakeClock()
    limiter = RateLimiter(rate_per_sec=1, capacity=1, now=clock.time, sleep=clock.sleep)

    limiter.acquire()  # drain the bucket
    gated_call(lambda: "ok", limiter=limiter)

    # Second call had to sleep because the bucket was empty.
    assert clock.sleeps == [pytest.approx(1.0)]


def test_gated_call_records_breaker_success():
    breaker = CircuitBreaker(failure_threshold=2, cooldown_s=10)
    breaker.record_failure()
    assert breaker.consecutive_failures == 1

    gated_call(lambda: "ok", breaker=breaker)
    assert breaker.consecutive_failures == 0


def test_gated_call_records_breaker_failure_and_reraises():
    breaker = CircuitBreaker(failure_threshold=2, cooldown_s=10)

    class _Boom(Exception):
        pass

    def _explode() -> None:
        raise _Boom("upstream hated us")

    with pytest.raises(_Boom):
        gated_call(_explode, breaker=breaker)
    assert breaker.consecutive_failures == 1


def test_gated_call_raises_circuit_open_without_invoking_fn():
    breaker = CircuitBreaker(failure_threshold=1, cooldown_s=10)
    breaker.record_failure()  # trip
    assert breaker.state == "open"

    invocations = 0

    def _fn() -> None:
        nonlocal invocations
        invocations += 1

    with pytest.raises(CircuitOpen):
        gated_call(_fn, breaker=breaker)
    assert invocations == 0


def test_failover_runs_rate_limiter_before_call():
    """The limiter sees one acquire() per attempted call, healthy or not."""
    calls: list[str] = []

    class _CountingLimiter(RateLimiter):
        def __init__(self, label: str, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._label = label

        def acquire(self) -> None:
            calls.append(self._label)
            super().acquire()

    primary = _new_heart("https://primary.example/rpc", _failing_web3())
    fallback = _new_heart(
        "https://fallback.example/rpc",
        _make_web3(84532, [_block(300, HASH_A, HASH_B)]),
    )

    labels = iter(["primary", "fallback"])

    def _limiter_factory() -> _CountingLimiter:
        return _CountingLimiter(next(labels), rate_per_sec=1000, capacity=1000)

    def _breaker_factory() -> CircuitBreaker:
        return CircuitBreaker(failure_threshold=1, cooldown_s=60)

    pool = FailoverRpcHeartbeat(
        [primary, fallback],
        limiter_factory=_limiter_factory,
        breaker_factory=_breaker_factory,
    )

    pool.tick()

    assert calls == ["primary", "fallback"]
