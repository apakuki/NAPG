"""Service Level Breach evaluation.

This is the rules-engine half of Phase 1: take the structured outputs of the
heartbeat / Aerodrome / Morpho probes and decide what counts as a breach.
The actions taken in response to breaches (alerting, autonomous migration)
land in later substeps; this module just produces a flat list of
machine-readable Breach records.

Thresholds load from `config/breaches.toml` by default. The model is the
source of truth; the TOML file mirrors its fields one-for-one.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from napg.monitor.aerodrome import LiquidityProbe
from napg.monitor.morpho import MorphoPoll
from napg.monitor.rpc import HeartbeatResult

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "breaches.toml"


class BreachThresholds(BaseModel):
    """Per-rule thresholds. Defaults are the same as `config/breaches.toml`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rpc_latency_ms_max: int = Field(default=2000, ge=0)
    block_age_seconds_max: int = Field(default=30, ge=0)
    reorg_is_breach: bool = True

    peg_deviation_bps_max: int = Field(default=50, ge=0)
    liquidity_required: bool = True

    market_utilization_bps_max: int = Field(default=9500, ge=0, le=10_000)
    market_staleness_seconds_max: int = Field(default=3600, ge=0)


class Breach(BaseModel):
    """One service level breach. Audit-log-ready: every field is JSON-safe."""

    model_config = ConfigDict(frozen=True)

    rule: str
    source: str
    severity: str = "warn"
    threshold: int | float | bool
    actual: int | float | bool
    message: str
    detected_at: float


def load_thresholds(path: Path | str | None = None) -> BreachThresholds:
    """Load thresholds from TOML, or return defaults when `path` is None.

    Passing an explicit path that doesn't exist raises FileNotFoundError —
    silently falling back would hide a config-rotation mistake.
    """
    if path is None:
        return BreachThresholds()
    path = Path(path)
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return BreachThresholds(**data)


def evaluate(
    thresholds: BreachThresholds,
    *,
    heartbeat: HeartbeatResult | None = None,
    liquidity: LiquidityProbe | None = None,
    morpho: MorphoPoll | None = None,
    now: float | None = None,
) -> tuple[Breach, ...]:
    """Run every applicable rule against the supplied probe outputs.

    `now` is injectable so the evaluator is deterministic in tests; in
    production callers pass `time.time()` or let it default. Block-age uses
    `now - block.timestamp`, which means a stale clock makes the agent more
    suspicious, not less — the right failure direction.
    """
    detected_at = now if now is not None else time.time()
    breaches: list[Breach] = []

    if heartbeat is not None:
        breaches.extend(_eval_heartbeat(thresholds, heartbeat, detected_at))
    if liquidity is not None:
        breaches.extend(_eval_liquidity(thresholds, liquidity, detected_at))
    if morpho is not None:
        breaches.extend(_eval_morpho(thresholds, morpho, detected_at))

    return tuple(breaches)


def _eval_heartbeat(
    thresholds: BreachThresholds,
    heartbeat: HeartbeatResult,
    detected_at: float,
) -> list[Breach]:
    out: list[Breach] = []
    if heartbeat.latency_ms > thresholds.rpc_latency_ms_max:
        out.append(
            Breach(
                rule="rpc_latency_ms_max",
                source="heartbeat",
                threshold=thresholds.rpc_latency_ms_max,
                actual=round(heartbeat.latency_ms, 2),
                message=(
                    f"RPC heartbeat latency {heartbeat.latency_ms:.1f} ms exceeds threshold "
                    f"{thresholds.rpc_latency_ms_max} ms"
                ),
                detected_at=detected_at,
            )
        )
    block_age = int(detected_at - heartbeat.block.timestamp)
    if block_age > thresholds.block_age_seconds_max:
        out.append(
            Breach(
                rule="block_age_seconds_max",
                source="heartbeat",
                threshold=thresholds.block_age_seconds_max,
                actual=block_age,
                message=(
                    f"Latest block is {block_age}s old; threshold "
                    f"{thresholds.block_age_seconds_max}s"
                ),
                detected_at=detected_at,
            )
        )
    if thresholds.reorg_is_breach and heartbeat.reorg_detected:
        out.append(
            Breach(
                rule="reorg_is_breach",
                source="heartbeat",
                threshold=False,
                actual=True,
                message="RPC heartbeat reported a chain reorganisation",
                detected_at=detected_at,
            )
        )
    return out


def _eval_liquidity(
    thresholds: BreachThresholds,
    liquidity: LiquidityProbe,
    detected_at: float,
) -> list[Breach]:
    out: list[Breach] = []
    if thresholds.liquidity_required and not liquidity.liquidity_available:
        out.append(
            Breach(
                rule="liquidity_required",
                source="aerodrome",
                threshold=True,
                actual=False,
                message="0x reports no liquidity available for the probed pair",
                detected_at=detected_at,
            )
        )
    deviation = liquidity.peg_deviation_bps
    if deviation is not None and deviation > thresholds.peg_deviation_bps_max:
        out.append(
            Breach(
                rule="peg_deviation_bps_max",
                source="aerodrome",
                threshold=thresholds.peg_deviation_bps_max,
                actual=deviation,
                message=(
                    f"Aerodrome USDC/USDT peg deviation {deviation} bps exceeds threshold "
                    f"{thresholds.peg_deviation_bps_max} bps"
                ),
                detected_at=detected_at,
            )
        )
    return out


def _eval_morpho(
    thresholds: BreachThresholds,
    morpho: MorphoPoll,
    detected_at: float,
) -> list[Breach]:
    out: list[Breach] = []
    for market in morpho.markets:
        source = f"morpho:{market.label}"
        if market.utilization_bps > thresholds.market_utilization_bps_max:
            out.append(
                Breach(
                    rule="market_utilization_bps_max",
                    source=source,
                    threshold=thresholds.market_utilization_bps_max,
                    actual=market.utilization_bps,
                    message=(
                        f"Morpho {market.label} utilisation {market.utilization_bps} bps "
                        f"exceeds threshold {thresholds.market_utilization_bps_max} bps"
                    ),
                    detected_at=detected_at,
                )
            )
        if market.staleness_seconds > thresholds.market_staleness_seconds_max:
            out.append(
                Breach(
                    rule="market_staleness_seconds_max",
                    source=source,
                    threshold=thresholds.market_staleness_seconds_max,
                    actual=market.staleness_seconds,
                    message=(
                        f"Morpho {market.label} accrual state is {market.staleness_seconds}s old "
                        f"(threshold {thresholds.market_staleness_seconds_max}s)"
                    ),
                    detected_at=detected_at,
                )
            )
    return out


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "Breach",
    "BreachThresholds",
    "evaluate",
    "load_thresholds",
]
