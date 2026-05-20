"""Unit tests for napg.monitor.morpho — Morpho Blue market reads on Base."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from napg.monitor.morpho import (
    BASE_CHAIN_ID,
    DEFAULT_TARGETS,
    MORPHO_BLUE_BASE,
    WETH_USDC_MARKET_ID,
    MarketState,
    MarketTarget,
    MorphoMonitor,
)


# Morpho Blue `market(bytes32)` returns:
#   (totalSupplyAssets, totalSupplyShares, totalBorrowAssets,
#    totalBorrowShares, lastUpdate, fee)
def _market_tuple(
    total_supply_assets: int,
    total_borrow_assets: int,
    last_update: int,
    total_supply_shares: int = 0,
    total_borrow_shares: int = 0,
    fee: int = 0,
) -> tuple[int, int, int, int, int, int]:
    return (
        total_supply_assets,
        total_supply_shares,
        total_borrow_assets,
        total_borrow_shares,
        last_update,
        fee,
    )


def _build_web3(
    block_number: int,
    block_timestamp: int,
    market_returns: dict[bytes, tuple[int, int, int, int, int, int]],
) -> MagicMock:
    """Construct a Web3 mock whose Morpho Blue contract returns canned values."""

    web3 = MagicMock()
    web3.eth.get_block.return_value = {
        "number": block_number,
        "timestamp": block_timestamp,
    }

    def make_market_fn(market_id: bytes) -> MagicMock:
        call = MagicMock()
        call.call.return_value = market_returns[market_id]
        return call

    contract = MagicMock()
    contract.functions.market.side_effect = make_market_fn
    web3.eth.contract.return_value = contract
    # Web3.to_checksum_address is a static, real implementation; the mock's
    # contract factory accepts whatever we give it.
    return web3


def _market_id_bytes(hex_str: str) -> bytes:
    return bytes.fromhex(hex_str[2:])


def test_https_required():
    with pytest.raises(ValueError, match="https"):
        MorphoMonitor("http://insecure.example/rpc")


def test_at_least_one_target_required():
    with pytest.raises(ValueError, match="market target"):
        MorphoMonitor("https://example.com/rpc", web3=MagicMock(), targets=[])


def test_tick_reads_all_targets_and_computes_utilisation():
    block_ts = 1_716_000_000
    block_no = 46_200_000

    weth_id = _market_id_bytes(DEFAULT_TARGETS[0].market_id)
    cbbtc_id = _market_id_bytes(DEFAULT_TARGETS[1].market_id)
    market_returns = {
        weth_id: _market_tuple(
            total_supply_assets=10_000_000 * 10**6,  # 10M USDC supplied
            total_borrow_assets=8_000_000 * 10**6,  # 8M USDC borrowed → 80% util
            last_update=block_ts - 30,  # 30s old
        ),
        cbbtc_id: _market_tuple(
            total_supply_assets=5_000_000 * 10**6,
            total_borrow_assets=2_500_000 * 10**6,  # 50% utilisation
            last_update=block_ts - 5,
        ),
    }

    web3 = _build_web3(block_no, block_ts, market_returns)
    monitor = MorphoMonitor("https://base-mainnet.example/rpc", web3=web3)

    poll = monitor.tick()

    assert poll.chain_id == BASE_CHAIN_ID
    assert poll.block_number == block_no
    assert poll.block_timestamp == block_ts
    assert poll.latency_ms >= 0
    assert poll.observed_at > 0

    by_label = {m.label: m for m in poll.markets}
    weth = by_label["WETH-USDC"]
    cbbtc = by_label["cbBTC-USDC"]

    assert weth.total_supply_assets == 10_000_000 * 10**6
    assert weth.total_borrow_assets == 8_000_000 * 10**6
    assert weth.utilization_bps == 8_000
    assert weth.staleness_seconds == 30
    assert weth.loan_symbol == "USDC"
    assert weth.collateral_symbol == "WETH"

    assert cbbtc.utilization_bps == 5_000
    assert cbbtc.staleness_seconds == 5
    assert cbbtc.collateral_symbol == "cbBTC"


def test_utilisation_zero_when_no_supply():
    block_ts = 1_716_000_000
    weth_id = _market_id_bytes(DEFAULT_TARGETS[0].market_id)
    cbbtc_id = _market_id_bytes(DEFAULT_TARGETS[1].market_id)
    web3 = _build_web3(
        100,
        block_ts,
        {
            weth_id: _market_tuple(0, 0, block_ts),
            cbbtc_id: _market_tuple(0, 0, block_ts),
        },
    )
    monitor = MorphoMonitor("https://base-mainnet.example/rpc", web3=web3)

    poll = monitor.tick()
    assert all(m.utilization_bps == 0 for m in poll.markets)


def test_utilisation_caps_at_10000_when_borrow_exceeds_supply():
    block_ts = 1_716_000_000
    weth_id = _market_id_bytes(DEFAULT_TARGETS[0].market_id)
    cbbtc_id = _market_id_bytes(DEFAULT_TARGETS[1].market_id)
    web3 = _build_web3(
        100,
        block_ts,
        {
            weth_id: _market_tuple(100, 200, block_ts),
            cbbtc_id: _market_tuple(100, 100, block_ts),
        },
    )
    monitor = MorphoMonitor("https://base-mainnet.example/rpc", web3=web3)

    poll = monitor.tick()
    by_label = {m.label: m for m in poll.markets}
    assert by_label["WETH-USDC"].utilization_bps == 10_000
    assert by_label["cbBTC-USDC"].utilization_bps == 10_000


def test_staleness_floors_at_zero_if_clock_skew():
    block_ts = 1_716_000_000
    weth_id = _market_id_bytes(DEFAULT_TARGETS[0].market_id)
    cbbtc_id = _market_id_bytes(DEFAULT_TARGETS[1].market_id)
    web3 = _build_web3(
        100,
        block_ts,
        {
            # Update timestamp ahead of block: clamp to 0 rather than report
            # a negative age that would fail schema validation.
            weth_id: _market_tuple(100, 50, block_ts + 60),
            cbbtc_id: _market_tuple(100, 50, block_ts),
        },
    )
    monitor = MorphoMonitor("https://base-mainnet.example/rpc", web3=web3)

    poll = monitor.tick()
    by_label = {m.label: m for m in poll.markets}
    assert by_label["WETH-USDC"].staleness_seconds == 0


def test_market_id_must_be_32_bytes():
    block_ts = 1_716_000_000
    bad_target = MarketTarget(
        label="bad",
        market_id="0xdeadbeef",  # 4 bytes, not 32
        loan_token=DEFAULT_TARGETS[0].loan_token,
        loan_symbol="USDC",
        collateral_token=DEFAULT_TARGETS[0].collateral_token,
        collateral_symbol="WETH",
    )
    web3 = _build_web3(100, block_ts, {})
    monitor = MorphoMonitor(
        "https://base-mainnet.example/rpc",
        web3=web3,
        targets=[bad_target],
    )
    with pytest.raises(ValueError, match="32 bytes"):
        monitor.tick()


def test_market_id_requires_0x_prefix():
    bad_target = MarketTarget(
        label="bad",
        market_id="deadbeef" * 8,  # 32 bytes worth of hex but no 0x
        loan_token=DEFAULT_TARGETS[0].loan_token,
        loan_symbol="USDC",
        collateral_token=DEFAULT_TARGETS[0].collateral_token,
        collateral_symbol="WETH",
    )
    web3 = _build_web3(100, 0, {})
    monitor = MorphoMonitor(
        "https://base-mainnet.example/rpc",
        web3=web3,
        targets=[bad_target],
    )
    with pytest.raises(ValueError, match="0x-prefixed"):
        monitor.tick()


def test_market_state_rejects_invalid_utilisation():
    with pytest.raises(ValidationError):
        MarketState(
            label="x",
            market_id=WETH_USDC_MARKET_ID,
            loan_symbol="USDC",
            collateral_symbol="WETH",
            total_supply_assets=0,
            total_borrow_assets=0,
            utilization_bps=10_001,  # outside [0, 10_000]
            last_update=1,
            staleness_seconds=0,
            block_number=1,
            observed_at=1.0,
        )


def test_contract_constructed_with_morpho_blue_address():
    captured: dict[str, Any] = {}

    web3 = MagicMock()
    web3.eth.get_block.return_value = {"number": 1, "timestamp": 1_716_000_000}

    def _capture_contract(address: str, abi: list[dict[str, Any]]) -> MagicMock:
        captured["address"] = address
        captured["abi"] = abi
        contract = MagicMock()
        contract.functions.market.return_value.call.return_value = _market_tuple(0, 0, 0)
        return contract

    web3.eth.contract.side_effect = _capture_contract

    monitor = MorphoMonitor("https://base-mainnet.example/rpc", web3=web3)
    monitor.tick()

    assert captured["address"].lower() == MORPHO_BLUE_BASE.lower()
    assert any(entry["name"] == "market" for entry in captured["abi"])


def test_tick_trips_breaker_on_failure_and_short_circuits_next_call():
    from napg.monitor.resilience import CircuitBreaker, CircuitOpen

    web3 = MagicMock()
    web3.eth.get_block.side_effect = RuntimeError("provider down")

    breaker = CircuitBreaker(failure_threshold=1, cooldown_s=60)
    monitor = MorphoMonitor(
        "https://base-mainnet.example/rpc",
        web3=web3,
        breaker=breaker,
    )

    with pytest.raises(RuntimeError, match="provider down"):
        monitor.tick()

    # Breaker is open; next call short-circuits without touching the upstream.
    with pytest.raises(CircuitOpen):
        monitor.tick()
    assert web3.eth.get_block.call_count == 1


def test_tick_calls_limiter_acquire():
    from napg.monitor.resilience import RateLimiter

    web3 = MagicMock()
    web3.eth.get_block.return_value = {"number": 1, "timestamp": 1}
    contract = MagicMock()
    contract.functions.market.return_value.call.return_value = _market_tuple(0, 0, 0)
    web3.eth.contract.return_value = contract

    acquired: list[int] = []

    class _Counting(RateLimiter):
        def acquire(self) -> None:
            acquired.append(1)
            super().acquire()

    limiter = _Counting(rate_per_sec=1000, capacity=1000)
    monitor = MorphoMonitor(
        "https://base-mainnet.example/rpc",
        web3=web3,
        limiter=limiter,
    )

    monitor.tick()
    assert acquired == [1]
