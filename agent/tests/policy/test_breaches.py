"""Unit tests for napg.policy.breaches — threshold loading and rule evaluation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from napg.monitor.aerodrome import LiquidityProbe
from napg.monitor.morpho import MarketState, MorphoPoll
from napg.monitor.rpc import BlockSnapshot, HeartbeatResult
from napg.policy.breaches import (
    DEFAULT_CONFIG_PATH,
    Breach,
    BreachThresholds,
    evaluate,
    load_thresholds,
)

HASH_A = "0x" + "aa" * 32
HASH_B = "0x" + "bb" * 32


def _heartbeat(
    latency_ms: float = 100.0,
    block_timestamp: int = 1_716_000_000,
    reorg_detected: bool = False,
    observed_at: float = 1_716_000_000.5,
) -> HeartbeatResult:
    block = BlockSnapshot(
        number=10,
        hash=HASH_A,
        parent_hash=HASH_B,
        timestamp=block_timestamp,
    )
    return HeartbeatResult(
        rpc_url="https://example/<redacted>",
        chain_id=84532,
        latency_ms=latency_ms,
        block=block,
        reorg_detected=reorg_detected,
        observed_at=observed_at,
    )


def _liquidity(
    liquidity_available: bool = True,
    peg_deviation_bps: int | None = 6,
    sell_amount: int = 10_000 * 10**6,
    buy_amount: int = 9_994 * 10**6,
) -> LiquidityProbe:
    return LiquidityProbe(
        chain_id=8453,
        sell_token="0x" + "11" * 20,
        buy_token="0x" + "22" * 20,
        sell_amount=sell_amount,
        buy_amount=buy_amount,
        liquidity_available=liquidity_available,
        quoted_rate=0.9994,
        peg_deviation_bps=peg_deviation_bps,
        sources=("Aerodrome_V3",),
        block_number=46_200_000,
        latency_ms=200.0,
        observed_at=1_716_000_000.0,
    )


def _market(
    label: str = "WETH-USDC",
    utilization_bps: int = 8_000,
    staleness_seconds: int = 30,
) -> MarketState:
    return MarketState(
        label=label,
        market_id="0x" + "ab" * 32,
        loan_symbol="USDC",
        collateral_symbol="WETH",
        total_supply_assets=10_000_000 * 10**6,
        total_borrow_assets=int(10_000_000 * 10**6 * utilization_bps / 10_000),
        utilization_bps=utilization_bps,
        last_update=1_716_000_000 - staleness_seconds,
        staleness_seconds=staleness_seconds,
        block_number=46_200_000,
        observed_at=1_716_000_000.0,
    )


def _poll(*markets: MarketState) -> MorphoPoll:
    return MorphoPoll(
        chain_id=8453,
        block_number=46_200_000,
        block_timestamp=1_716_000_000,
        markets=markets,
        latency_ms=1500.0,
        observed_at=1_716_000_000.0,
    )


# --- defaults & loading ---------------------------------------------------


def test_defaults_match_packaged_toml():
    """The defaults in the model must equal what's in config/breaches.toml."""
    defaults = BreachThresholds()
    from_file = load_thresholds(DEFAULT_CONFIG_PATH)
    assert defaults == from_file


def test_load_thresholds_none_returns_defaults():
    assert load_thresholds(None) == BreachThresholds()


def test_load_thresholds_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_thresholds(tmp_path / "nope.toml")


def test_load_thresholds_overrides(tmp_path: Path):
    path = tmp_path / "custom.toml"
    path.write_text(
        "\n".join(
            [
                "rpc_latency_ms_max = 500",
                "peg_deviation_bps_max = 25",
                "market_utilization_bps_max = 8500",
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_thresholds(path)
    assert loaded.rpc_latency_ms_max == 500
    assert loaded.peg_deviation_bps_max == 25
    assert loaded.market_utilization_bps_max == 8500
    # Unspecified fields stay at defaults.
    assert loaded.market_staleness_seconds_max == 3600


def test_load_thresholds_rejects_unknown_field(tmp_path: Path):
    path = tmp_path / "bad.toml"
    path.write_text("typo_field = 1\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_thresholds(path)


def test_utilisation_threshold_bounded_to_10000():
    with pytest.raises(ValidationError):
        BreachThresholds(market_utilization_bps_max=10_001)


# --- evaluator: no input → no breaches ------------------------------------


def test_no_inputs_returns_empty():
    assert evaluate(BreachThresholds()) == ()


def test_all_inputs_within_threshold_returns_empty():
    thresholds = BreachThresholds()
    now = 1_716_000_010.0  # 10s after the block timestamp; well within block_age_seconds_max

    out = evaluate(
        thresholds,
        heartbeat=_heartbeat(latency_ms=100.0, block_timestamp=1_716_000_000),
        liquidity=_liquidity(liquidity_available=True, peg_deviation_bps=6),
        morpho=_poll(_market("WETH-USDC", 8_000, 30), _market("cbBTC-USDC", 8_900, 4)),
        now=now,
    )
    assert out == ()


# --- evaluator: heartbeat rules -------------------------------------------


def test_latency_breach_fires():
    out = evaluate(
        BreachThresholds(),
        heartbeat=_heartbeat(latency_ms=3500.0),
        now=1_716_000_010.0,
    )
    rules = {b.rule for b in out}
    assert "rpc_latency_ms_max" in rules


def test_latency_exactly_at_threshold_does_not_fire():
    out = evaluate(
        BreachThresholds(rpc_latency_ms_max=2000),
        heartbeat=_heartbeat(latency_ms=2000.0),
        now=1_716_000_010.0,
    )
    assert all(b.rule != "rpc_latency_ms_max" for b in out)


def test_block_age_breach_fires():
    out = evaluate(
        BreachThresholds(),
        heartbeat=_heartbeat(block_timestamp=1_716_000_000),
        now=1_716_000_000 + 120,  # 120s after the block
    )
    rules = {b.rule for b in out}
    assert "block_age_seconds_max" in rules


def test_reorg_breach_fires_when_enabled():
    out = evaluate(
        BreachThresholds(),
        heartbeat=_heartbeat(reorg_detected=True),
        now=1_716_000_010.0,
    )
    assert any(b.rule == "reorg_is_breach" for b in out)


def test_reorg_breach_suppressed_when_disabled():
    out = evaluate(
        BreachThresholds(reorg_is_breach=False),
        heartbeat=_heartbeat(reorg_detected=True),
        now=1_716_000_010.0,
    )
    assert all(b.rule != "reorg_is_breach" for b in out)


# --- evaluator: aerodrome rules -------------------------------------------


def test_liquidity_unavailable_breach_fires():
    out = evaluate(
        BreachThresholds(),
        liquidity=_liquidity(liquidity_available=False, peg_deviation_bps=None),
        now=1_716_000_010.0,
    )
    assert any(b.rule == "liquidity_required" for b in out)


def test_peg_deviation_breach_fires():
    out = evaluate(
        BreachThresholds(peg_deviation_bps_max=10),
        liquidity=_liquidity(peg_deviation_bps=25),
        now=1_716_000_010.0,
    )
    assert any(b.rule == "peg_deviation_bps_max" for b in out)


def test_peg_deviation_none_is_not_a_breach():
    out = evaluate(
        BreachThresholds(),
        liquidity=_liquidity(liquidity_available=True, peg_deviation_bps=None),
        now=1_716_000_010.0,
    )
    assert all(b.rule != "peg_deviation_bps_max" for b in out)


# --- evaluator: morpho rules ----------------------------------------------


def test_morpho_utilisation_breach_fires_per_market():
    out = evaluate(
        BreachThresholds(market_utilization_bps_max=9000),
        morpho=_poll(
            _market("WETH-USDC", utilization_bps=8_500, staleness_seconds=30),
            _market("cbBTC-USDC", utilization_bps=9_500, staleness_seconds=4),
        ),
        now=1_716_000_010.0,
    )
    util_breaches = [b for b in out if b.rule == "market_utilization_bps_max"]
    assert len(util_breaches) == 1
    assert util_breaches[0].source == "morpho:cbBTC-USDC"
    assert util_breaches[0].actual == 9_500


def test_morpho_staleness_breach_fires_per_market():
    out = evaluate(
        BreachThresholds(market_staleness_seconds_max=60),
        morpho=_poll(
            _market("WETH-USDC", utilization_bps=5_000, staleness_seconds=30),
            _market("cbBTC-USDC", utilization_bps=5_000, staleness_seconds=900),
        ),
        now=1_716_000_010.0,
    )
    stale = [b for b in out if b.rule == "market_staleness_seconds_max"]
    assert len(stale) == 1
    assert stale[0].source == "morpho:cbBTC-USDC"
    assert stale[0].actual == 900


# --- breach record shape --------------------------------------------------


def test_breach_record_has_audit_safe_fields():
    out = evaluate(
        BreachThresholds(rpc_latency_ms_max=10),
        heartbeat=_heartbeat(latency_ms=5_000.0),
        now=1_716_000_010.0,
    )
    assert len(out) == 1
    breach = out[0]
    assert isinstance(breach, Breach)
    assert breach.severity == "warn"
    assert breach.detected_at == 1_716_000_010.0
    # Audit serialiser should never touch live objects; model_dump_json proves
    # every field round-trips to JSON-safe primitives.
    dumped = breach.model_dump_json()
    assert "rpc_latency_ms_max" in dumped
    assert "5000.0" in dumped or "5000" in dumped


def test_multiple_breaches_returned_in_a_single_pass():
    out = evaluate(
        BreachThresholds(
            rpc_latency_ms_max=10,
            peg_deviation_bps_max=1,
            market_utilization_bps_max=1,
        ),
        heartbeat=_heartbeat(latency_ms=200.0),
        liquidity=_liquidity(peg_deviation_bps=15),
        morpho=_poll(_market(utilization_bps=9_000)),
        now=1_716_000_010.0,
    )
    rules = {b.rule for b in out}
    assert {"rpc_latency_ms_max", "peg_deviation_bps_max", "market_utilization_bps_max"} <= rules
