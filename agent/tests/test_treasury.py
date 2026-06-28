"""Tests for napg.treasury — concentration assessment, distance-to-breach, breach."""

from __future__ import annotations

from napg.treasury import (
    TreasuryLimits,
    TreasuryPosition,
    assess_treasury,
    evaluate_treasury,
    load_treasury_limits,
)


def _pos(protocol: str, issuer: str, value: int, *, is_stablecoin: bool = True) -> TreasuryPosition:
    return TreasuryPosition(
        protocol=protocol,
        chain="base-mainnet",
        issuer=issuer,
        symbol="USDC",
        value=value,
        is_stablecoin=is_stablecoin,
    )


def test_defaults_mirror_policy():
    limits = TreasuryLimits()
    assert limits.max_single_protocol_bps == 4_000
    assert limits.max_stablecoin_bps == 6_000
    assert limits.max_single_issuer_bps == 10_000
    assert limits.max_acceptable_permanent_loss_bps == 500


def test_load_treasury_limits_defaults_when_none():
    assert load_treasury_limits(None).max_single_protocol_bps == 4_000


def test_committed_treasury_toml_loads():
    limits = load_treasury_limits(
        __import__("napg.treasury", fromlist=["DEFAULT_CONFIG_PATH"]).DEFAULT_CONFIG_PATH
    )
    assert limits.max_single_protocol_bps == 4_000
    assert limits.max_acceptable_permanent_loss_bps == 500


def test_protocol_concentration_within_limit_no_breach():
    # Spread across protocols/issuers and keep stablecoin share <= 60% so no
    # dimension breaches; idle sits exactly on the 40% protocol limit.
    positions = (
        _pos("aerodrome", "circle", 30, is_stablecoin=True),
        _pos("morpho", "tether", 30, is_stablecoin=False),
        _pos("idle", "maker", 40, is_stablecoin=False),
    )
    snapshot = assess_treasury(positions, TreasuryLimits(), observed_at=1.0)
    assert snapshot.any_breached is False
    idle = next(e for e in snapshot.per_protocol if e.key == "idle")
    assert idle.bps == 4_000  # exactly on the 40% limit
    assert idle.headroom_bps == 0
    assert idle.breached is False


def test_protocol_over_limit_breaches():
    # Non-stable, single issuer (100% == limit, not over) -> only the two
    # protocol exposures breach.
    positions = (
        _pos("aerodrome", "circle", 50, is_stablecoin=False),
        _pos("morpho", "circle", 50, is_stablecoin=False),
    )
    snapshot = assess_treasury(positions, TreasuryLimits(), observed_at=2.0)
    assert snapshot.any_breached is True
    breaches = evaluate_treasury(snapshot, detected_at=2.0)
    assert len(breaches) == 2  # both protocols at 50% > 40%
    b = breaches[0]
    assert b.rule == "treasury_concentration_bps_max"
    assert b.source == "treasury"
    assert b.actual == 5_000
    assert b.threshold == 4_000


def test_headroom_tracks_distance_to_breach():
    # All dimensions within limits; aerodrome creeps to 39.8%, the tightest.
    positions = (
        _pos("aerodrome", "circle", 398, is_stablecoin=True),
        _pos("morpho", "tether", 300, is_stablecoin=False),
        _pos("idle", "maker", 302, is_stablecoin=False),
    )
    snapshot = assess_treasury(positions, TreasuryLimits(), observed_at=3.0)
    assert snapshot.any_breached is False
    aero = next(e for e in snapshot.per_protocol if e.key == "aerodrome")
    assert aero.bps == 3_980  # 39.8%
    assert aero.headroom_bps == 20  # 20 bps from the 40% limit
    assert aero.breached is False
    # worst headroom across all dimensions is the tightest distance-to-breach.
    assert snapshot.worst_headroom_bps == 20


def test_stablecoin_concentration_breaches():
    positions = (
        _pos("aerodrome", "circle", 70, is_stablecoin=True),
        _pos("aave", "weth", 30, is_stablecoin=False),
    )
    snapshot = assess_treasury(positions, TreasuryLimits(), observed_at=4.0)
    assert snapshot.stablecoin.bps == 7_000  # 70% > 60%
    assert snapshot.stablecoin.breached is True
    breaches = evaluate_treasury(snapshot, detected_at=4.0)
    assert any("stablecoin" in b.message for b in breaches)


def test_issuer_breach_with_tightened_limit():
    limits = TreasuryLimits(max_single_issuer_bps=6_000)  # tighten from 100%
    positions = (_pos("aerodrome", "circle", 80), _pos("aave", "maker", 20))
    snapshot = assess_treasury(positions, limits, observed_at=5.0)
    circle = next(e for e in snapshot.per_issuer if e.key == "circle")
    assert circle.bps == 8_000
    assert circle.breached is True


def test_empty_treasury_is_inert():
    snapshot = assess_treasury((), TreasuryLimits(), observed_at=6.0)
    assert snapshot.total_value == 0
    assert snapshot.any_breached is False
    assert evaluate_treasury(snapshot, detected_at=6.0) == ()
