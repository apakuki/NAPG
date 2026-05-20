"""Unit tests for napg.monitor.aerodrome — 0x probe schema, headers, peg math."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from napg.monitor.aerodrome import (
    BASE_CHAIN_ID,
    DEFAULT_PROBE_AMOUNT_USDC,
    USDC_BASE_MAINNET,
    USDT_BASE_MAINNET,
    AerodromeMonitor,
)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok_response(
    sell_amount: int = DEFAULT_PROBE_AMOUNT_USDC,
    buy_amount: int = DEFAULT_PROBE_AMOUNT_USDC,
    sources: tuple[str, ...] = ("Aerodrome_V3",),
    block_number: int = 12_345_678,
    liquidity_available: bool = True,
) -> dict:
    return {
        "liquidityAvailable": liquidity_available,
        "blockNumber": str(block_number),
        "sellAmount": str(sell_amount),
        "buyAmount": str(buy_amount),
        "minBuyAmount": str(int(buy_amount * 0.99)),
        "route": {
            "fills": [{"source": s, "proportionBps": str(10_000 // len(sources))} for s in sources],
        },
        # Extra field 0x might add; probe must ignore it.
        "unknownFutureField": "ignore me",
    }


def test_missing_api_key_raises():
    with pytest.raises(ValueError, match="0x API key"):
        AerodromeMonitor(api_key="")


def test_non_positive_amount_rejected():
    with pytest.raises(ValueError, match="sell_amount"):
        AerodromeMonitor(api_key="k", sell_amount=0)


def test_tick_happy_path_perfect_peg():
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200, json=_ok_response())

    monitor = AerodromeMonitor(api_key="secret-key", http=_client(handler))
    probe = monitor.tick()

    assert probe.chain_id == BASE_CHAIN_ID
    assert probe.sell_token == USDC_BASE_MAINNET
    assert probe.buy_token == USDT_BASE_MAINNET
    assert probe.liquidity_available is True
    assert probe.sell_amount == DEFAULT_PROBE_AMOUNT_USDC
    assert probe.buy_amount == DEFAULT_PROBE_AMOUNT_USDC
    assert probe.quoted_rate == pytest.approx(1.0)
    assert probe.peg_deviation_bps == 0
    assert probe.sources == ("Aerodrome_V3",)
    assert probe.block_number == 12_345_678
    assert probe.latency_ms >= 0
    assert probe.observed_at > 0


def test_request_carries_required_headers_and_params():
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200, json=_ok_response())

    AerodromeMonitor(api_key="secret-key", http=_client(handler)).tick()

    req = captured["req"]
    assert req.headers["0x-api-key"] == "secret-key"
    assert req.headers["0x-version"] == "v2"
    assert req.url.params["chainId"] == str(BASE_CHAIN_ID)
    assert req.url.params["sellToken"] == USDC_BASE_MAINNET
    assert req.url.params["buyToken"] == USDT_BASE_MAINNET
    assert req.url.params["sellAmount"] == str(DEFAULT_PROBE_AMOUNT_USDC)


def test_slight_depeg_reports_bps():
    # 9_990 USDT out for 10_000 USDC in → 10 bps depeg.
    body = _ok_response(
        sell_amount=10_000 * 10**6,
        buy_amount=9_990 * 10**6,
    )

    monitor = AerodromeMonitor(
        api_key="k",
        http=_client(lambda _r: httpx.Response(200, json=body)),
    )
    probe = monitor.tick()

    assert probe.quoted_rate == pytest.approx(0.999)
    assert probe.peg_deviation_bps == 10


def test_no_liquidity_available():
    body = {
        "liquidityAvailable": False,
        "blockNumber": "12345678",
        "sellAmount": "0",
        "buyAmount": "0",
        "minBuyAmount": "0",
        "route": {"fills": []},
    }
    monitor = AerodromeMonitor(
        api_key="k",
        http=_client(lambda _r: httpx.Response(200, json=body)),
    )
    probe = monitor.tick()

    assert probe.liquidity_available is False
    assert probe.quoted_rate is None
    assert probe.peg_deviation_bps is None
    assert probe.sources == ()


def test_multi_source_route_extracted_in_order():
    body = _ok_response(sources=("Aerodrome_V3", "Uniswap_V3", "BaseSwap"))
    monitor = AerodromeMonitor(
        api_key="k",
        http=_client(lambda _r: httpx.Response(200, json=body)),
    )
    probe = monitor.tick()

    assert probe.sources == ("Aerodrome_V3", "Uniswap_V3", "BaseSwap")


def test_non_200_raises_with_status_and_body():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text='{"error":"invalid api key"}')

    monitor = AerodromeMonitor(api_key="bad", http=_client(handler))
    with pytest.raises(RuntimeError, match="401"):
        monitor.tick()


def test_custom_pair_and_amount_passed_through():
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200, json=_ok_response())

    custom_sell = "0x" + "11" * 20
    custom_buy = "0x" + "22" * 20
    AerodromeMonitor(
        api_key="k",
        http=_client(handler),
        sell_token=custom_sell,
        buy_token=custom_buy,
        sell_amount=500_000,
    ).tick()

    params = captured["req"].url.params
    assert params["sellToken"] == custom_sell
    assert params["buyToken"] == custom_buy
    assert params["sellAmount"] == "500000"


def test_response_string_integers_coerce():
    """0x returns numeric values as JSON strings — schema must coerce to int."""
    body = _ok_response()
    body["buyAmount"] = "9999000000"  # string, not int
    body["blockNumber"] = "987654321"

    monitor = AerodromeMonitor(
        api_key="k",
        http=_client(lambda _r: httpx.Response(200, json=body)),
    )
    probe = monitor.tick()

    assert probe.buy_amount == 9_999_000_000
    assert probe.block_number == 987_654_321


def test_tick_trips_breaker_on_http_error_and_short_circuits():
    from napg.monitor.resilience import CircuitBreaker, CircuitOpen

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    breaker = CircuitBreaker(failure_threshold=1, cooldown_s=60)
    monitor = AerodromeMonitor(
        api_key="k",
        http=_client(handler),
        breaker=breaker,
    )

    with pytest.raises(RuntimeError, match="429"):
        monitor.tick()

    with pytest.raises(CircuitOpen):
        monitor.tick()


def test_tick_calls_limiter_acquire():
    from napg.monitor.resilience import RateLimiter

    acquired: list[int] = []

    class _Counting(RateLimiter):
        def acquire(self) -> None:
            acquired.append(1)
            super().acquire()

    monitor = AerodromeMonitor(
        api_key="k",
        http=_client(lambda _r: httpx.Response(200, json=_ok_response())),
        limiter=_Counting(rate_per_sec=1000, capacity=1000),
    )

    monitor.tick()
    assert acquired == [1]
