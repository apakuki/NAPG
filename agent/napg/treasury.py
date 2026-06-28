"""Treasury concentration enforcement.

Phase 4 Group F. The treasury policy in docs/treasury-policy.md is a written
*risk appetite* — how much can we lose (5%), how concentrated can we be (per
protocol 40%, stablecoin 60%), how long can Base disappear (24h). This module
turns that appetite into running enforcement: take the current positions, compute
exposures, and raise a breach when a limit is crossed.

Two things make this useful beyond a single check:

- **Append-only snapshots.** Every assessment can be written to the audit log
  (`treasury_snapshot` kind). Six months on, the history answers "how did we
  gradually end up 70% concentrated?" — which a point-in-time check never can.
- **Distance-to-breach (`headroom_bps`).** Each exposure reports how far it sits
  below its limit, so you can watch a number trend toward a breach (39% -> 39.8%
  -> 40.2%) across snapshots, not just learn about it at the moment it crosses.

There is no live treasury yet (testnet dust, 100% USDC by the documented launch
posture), so the on-chain balance poller that produces `TreasuryPosition`s lands
with a real treasury. This module is the grounded, fully-tested evaluation engine
it will feed.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from napg.policy.breaches import Breach

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]

_BPS = 10_000
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "treasury.toml"


class TreasuryLimits(BaseModel):
    """Risk-appetite limits, in basis points. Defaults mirror treasury-policy.md."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_single_protocol_bps: int = Field(default=4_000, ge=0, le=_BPS)  # 40%
    max_stablecoin_bps: int = Field(default=6_000, ge=0, le=_BPS)  # 60%
    max_single_issuer_bps: int = Field(default=10_000, ge=0, le=_BPS)  # 100% (launch)
    max_acceptable_permanent_loss_bps: int = Field(default=500, ge=0, le=_BPS)  # 5%


class TreasuryPosition(BaseModel):
    """One holding. `value` is in a common unit (e.g. USD cents); only ratios
    matter here, so the unit just has to be consistent across positions."""

    model_config = ConfigDict(frozen=True)

    protocol: str
    chain: str
    issuer: str
    symbol: str
    value: int = Field(ge=0)
    is_stablecoin: bool = True


class Exposure(BaseModel):
    """One dimension's concentration and how much room is left under its limit."""

    model_config = ConfigDict(frozen=True)

    key: str
    bps: int
    limit_bps: int
    headroom_bps: int  # limit - bps; negative means breached
    breached: bool


class TreasurySnapshot(BaseModel):
    """A point-in-time concentration assessment. Audit-log-ready (append-only)."""

    model_config = ConfigDict(frozen=True)

    observed_at: float
    total_value: int
    per_protocol: tuple[Exposure, ...]
    per_issuer: tuple[Exposure, ...]
    stablecoin: Exposure
    worst_headroom_bps: int | None  # smallest headroom across all dimensions
    any_breached: bool


def load_treasury_limits(path: Path | str | None = None) -> TreasuryLimits:
    """Load limits from TOML, or defaults when `path` is None."""
    if path is None:
        return TreasuryLimits()
    with Path(path).open("rb") as handle:
        return TreasuryLimits(**tomllib.load(handle))


def _bps(part: int, total: int) -> int:
    return round(part * _BPS / total) if total > 0 else 0


def _group_exposures(
    positions: tuple[TreasuryPosition, ...], total: int, key, limit_bps: int
) -> list[Exposure]:
    sums: dict[str, int] = {}
    for p in positions:
        sums[key(p)] = sums.get(key(p), 0) + p.value
    exposures = []
    for name, value in sorted(sums.items()):
        bps = _bps(value, total)
        exposures.append(
            Exposure(
                key=name,
                bps=bps,
                limit_bps=limit_bps,
                headroom_bps=limit_bps - bps,
                breached=bps > limit_bps,
            )
        )
    return exposures


def assess_treasury(
    positions: tuple[TreasuryPosition, ...],
    limits: TreasuryLimits,
    *,
    observed_at: float,
) -> TreasurySnapshot:
    """Compute exposures, distance-to-breach, and overall breach state. Pure."""
    total = sum(p.value for p in positions)
    per_protocol = tuple(
        _group_exposures(positions, total, lambda p: p.protocol, limits.max_single_protocol_bps)
    )
    per_issuer = tuple(
        _group_exposures(positions, total, lambda p: p.issuer, limits.max_single_issuer_bps)
    )
    stable_value = sum(p.value for p in positions if p.is_stablecoin)
    stable_bps = _bps(stable_value, total)
    stablecoin = Exposure(
        key="stablecoin",
        bps=stable_bps,
        limit_bps=limits.max_stablecoin_bps,
        headroom_bps=limits.max_stablecoin_bps - stable_bps,
        breached=stable_bps > limits.max_stablecoin_bps,
    )
    all_exposures = [*per_protocol, *per_issuer, stablecoin]
    worst_headroom = min((e.headroom_bps for e in all_exposures), default=None)
    return TreasurySnapshot(
        observed_at=observed_at,
        total_value=total,
        per_protocol=per_protocol,
        per_issuer=per_issuer,
        stablecoin=stablecoin,
        worst_headroom_bps=worst_headroom,
        any_breached=any(e.breached for e in all_exposures),
    )


def evaluate_treasury(snapshot: TreasurySnapshot, *, detected_at: float) -> tuple[Breach, ...]:
    """One `treasury_concentration_bps_max` breach per breached dimension."""
    breaches: list[Breach] = []
    dimensions = [*snapshot.per_protocol, *snapshot.per_issuer, snapshot.stablecoin]
    for exposure in dimensions:
        if not exposure.breached:
            continue
        breaches.append(
            Breach(
                rule="treasury_concentration_bps_max",
                source="treasury",
                threshold=exposure.limit_bps,
                actual=exposure.bps,
                message=(
                    f"treasury exposure '{exposure.key}' at {exposure.bps} bps exceeds limit "
                    f"{exposure.limit_bps} bps"
                ),
                detected_at=detected_at,
            )
        )
    return tuple(breaches)


__all__ = [
    "Exposure",
    "TreasuryLimits",
    "TreasuryPosition",
    "TreasurySnapshot",
    "assess_treasury",
    "evaluate_treasury",
    "load_treasury_limits",
]
