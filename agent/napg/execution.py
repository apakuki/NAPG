"""Post-trade swap execution quality.

Phase 4 Group E. Slippage bounds (Stage 2) cap *how much* a swap may lose before
its on-chain minOut reverts it; they do not tell you *whether* you were
sandwiched — you can be MEV'd inside tolerance and the tx still succeeds. This
module turns that invisible loss into a first-class, recorded Service Level
signal.

For every swap NAPG performs it records the dataset the reviewer asked for —
`quoted_out` (the pre-trade 0x quote), `simulated_out` (Stage 3 Tenderly sim, when
available), and `realized_out` (the on-chain receipt) — plus derived metrics. Six
months on, that dataset answers: are quotes systematically optimistic? is
Tenderly accurate? are we being MEV'd? is execution degrading? Adverse execution
that lands within slippage tolerance does not revert, so without this it would be
invisible; here it is auditable and can raise a `realized_slippage_bps_max`
breach.

`simulated_out_wei` is populated by the Stage 3 swap state-diff parser, which is
deferred to its own (security-critical, live-verified) PR; until then it is None
and the simulated-vs-realized metric is omitted, but the quoted-vs-realized
slippage and the breach work from the receipt alone.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from napg.policy.breaches import Breach, BreachThresholds

_BPS = 10_000


class SwapExecution(BaseModel):
    """One swap's quoted / simulated / realized outputs. The stored dataset."""

    model_config = ConfigDict(frozen=True)

    token_in: str
    token_out: str
    amount_in_wei: int = Field(ge=0)
    quoted_out_wei: int = Field(ge=0)
    realized_out_wei: int = Field(ge=0)
    simulated_out_wei: int | None = Field(default=None, ge=0)


class ExecutionQuality(BaseModel):
    """Derived execution-quality metrics for one swap. Audit-log-ready."""

    model_config = ConfigDict(frozen=True)

    # Positive bps = received less than quoted (adverse). Negative = positive
    # surprise (received more than quoted).
    realized_slippage_bps: int
    # How far the on-chain result drifted from the simulation. None when no sim.
    simulated_vs_realized_bps: int | None
    # Output units received per input unit (realized_out / amount_in).
    execution_price: float | None


def assess(execution: SwapExecution) -> ExecutionQuality:
    """Compute execution-quality metrics from a swap's outputs. Pure."""
    realized_slippage_bps = _bps_shortfall(execution.quoted_out_wei, execution.realized_out_wei)
    simulated_vs_realized_bps = (
        _bps_shortfall(execution.simulated_out_wei, execution.realized_out_wei)
        if execution.simulated_out_wei is not None
        else None
    )
    execution_price = (
        execution.realized_out_wei / execution.amount_in_wei
        if execution.amount_in_wei > 0
        else None
    )
    return ExecutionQuality(
        realized_slippage_bps=realized_slippage_bps,
        simulated_vs_realized_bps=simulated_vs_realized_bps,
        execution_price=execution_price,
    )


def _bps_shortfall(reference_wei: int, actual_wei: int) -> int:
    """Basis-point shortfall of `actual` below `reference`. 0 if reference is 0."""
    if reference_wei <= 0:
        return 0
    return round((reference_wei - actual_wei) * _BPS / reference_wei)


def evaluate_execution(
    thresholds: BreachThresholds,
    execution: SwapExecution,
    *,
    detected_at: float,
) -> tuple[Breach, ...]:
    """Emit a `realized_slippage_bps_max` breach when realized slippage exceeds
    the threshold. Returns () when execution was within tolerance."""
    quality = assess(execution)
    if quality.realized_slippage_bps <= thresholds.realized_slippage_bps_max:
        return ()
    return (
        Breach(
            rule="realized_slippage_bps_max",
            source="swap",
            threshold=thresholds.realized_slippage_bps_max,
            actual=quality.realized_slippage_bps,
            message=(
                f"swap realized slippage {quality.realized_slippage_bps} bps exceeds threshold "
                f"{thresholds.realized_slippage_bps_max} bps "
                f"(quoted {execution.quoted_out_wei}, received {execution.realized_out_wei})"
            ),
            detected_at=detected_at,
        ),
    )


def to_audit_payload(execution: SwapExecution, quality: ExecutionQuality) -> dict[str, object]:
    """The `swap_execution` audit-row dataset: raw outputs + derived metrics."""
    return {**execution.model_dump(), **quality.model_dump()}


__all__ = [
    "ExecutionQuality",
    "SwapExecution",
    "assess",
    "evaluate_execution",
    "to_audit_payload",
]
