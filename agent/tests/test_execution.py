"""Tests for napg.execution — post-trade swap execution quality + breach."""

from __future__ import annotations

from napg.execution import (
    SwapExecution,
    assess,
    evaluate_execution,
    to_audit_payload,
)
from napg.policy.breaches import BreachThresholds

TOKEN_IN = "0x" + "cc" * 20
TOKEN_OUT = "0x" + "dd" * 20


def _execution(
    *, quoted: int, realized: int, simulated: int | None = None, amount_in: int = 1_000_000
) -> SwapExecution:
    return SwapExecution(
        token_in=TOKEN_IN,
        token_out=TOKEN_OUT,
        amount_in_wei=amount_in,
        quoted_out_wei=quoted,
        realized_out_wei=realized,
        simulated_out_wei=simulated,
    )


def test_realized_slippage_bps_is_shortfall_vs_quote():
    q = assess(_execution(quoted=1_000_000, realized=995_000))
    assert q.realized_slippage_bps == 50  # 0.5%


def test_positive_surprise_is_negative_slippage():
    q = assess(_execution(quoted=1_000_000, realized=1_002_000))
    assert q.realized_slippage_bps == -20  # received more than quoted


def test_simulated_vs_realized_when_sim_present():
    q = assess(_execution(quoted=1_000_000, realized=990_000, simulated=1_000_000))
    assert q.simulated_vs_realized_bps == 100  # sim said 1.0M, got 0.99M


def test_simulated_vs_realized_none_without_sim():
    q = assess(_execution(quoted=1_000_000, realized=990_000))
    assert q.simulated_vs_realized_bps is None


def test_execution_price():
    q = assess(_execution(quoted=1_000_000, realized=2_000_000, amount_in=1_000_000))
    assert q.execution_price == 2.0


def test_execution_price_none_on_zero_input():
    q = assess(_execution(quoted=1, realized=1, amount_in=0))
    assert q.execution_price is None


def test_zero_quote_yields_zero_slippage():
    # Guard: a zero reference cannot be divided into; report 0, not a crash.
    q = assess(_execution(quoted=0, realized=0))
    assert q.realized_slippage_bps == 0


def test_no_breach_within_threshold():
    thresholds = BreachThresholds()  # realized_slippage_bps_max default 100
    breaches = evaluate_execution(
        thresholds, _execution(quoted=1_000_000, realized=995_000), detected_at=1.0
    )
    assert breaches == ()


def test_breach_when_realized_slippage_exceeds_threshold():
    thresholds = BreachThresholds()  # 100 bps cap
    breaches = evaluate_execution(
        thresholds, _execution(quoted=1_000_000, realized=980_000), detected_at=5.0
    )
    assert len(breaches) == 1
    b = breaches[0]
    assert b.rule == "realized_slippage_bps_max"
    assert b.source == "swap"
    assert b.actual == 200
    assert b.threshold == 100
    assert b.detected_at == 5.0


def test_to_audit_payload_carries_dataset_and_metrics():
    execution = _execution(quoted=1_000_000, realized=990_000, simulated=1_000_000)
    payload = to_audit_payload(execution, assess(execution))
    # The raw dataset the reviewer wants stored.
    assert payload["quoted_out_wei"] == 1_000_000
    assert payload["simulated_out_wei"] == 1_000_000
    assert payload["realized_out_wei"] == 990_000
    # Plus the derived metrics.
    assert payload["realized_slippage_bps"] == 100
    assert payload["simulated_vs_realized_bps"] == 100
