"""Unit tests for napg.scenarios — synthetic monitor outputs.

The scenario helpers are pure functions; these tests pin down their shape
so the orchestrator integration tests can rely on them.
"""

from __future__ import annotations

import pytest

from napg.policy.breaches import BreachThresholds, evaluate
from napg.scenarios import (
    BASE_SEPOLIA_CHAIN_ID,
    SYNTHETIC_RPC_URL,
    sequencer_delay_heartbeat,
)


def test_defaults_produce_a_stale_block_with_reorg() -> None:
    result = sequencer_delay_heartbeat(now=1_716_000_000.0)

    assert result.chain_id == BASE_SEPOLIA_CHAIN_ID
    assert result.rpc_url == SYNTHETIC_RPC_URL
    assert result.reorg_detected is True
    assert result.block.timestamp == 1_716_000_000 - 600
    assert result.latency_ms == 4500.0


def test_no_reorg_flag_disables_reorg_signal() -> None:
    result = sequencer_delay_heartbeat(include_reorg=False, now=1_716_000_000.0)
    assert result.reorg_detected is False


def test_negative_stale_seconds_rejected() -> None:
    with pytest.raises(ValueError, match="stale_seconds"):
        sequencer_delay_heartbeat(stale_seconds=-1)


def test_negative_latency_rejected() -> None:
    with pytest.raises(ValueError, match="latency_ms"):
        sequencer_delay_heartbeat(latency_ms=-0.1)


def test_zero_stale_seconds_produces_no_block_age_breach() -> None:
    """At stale_seconds=0 the block is fresh, so block-age must NOT trip."""
    result = sequencer_delay_heartbeat(
        stale_seconds=0, include_reorg=False, latency_ms=100.0, now=1_716_000_000.0
    )
    breaches = evaluate(BreachThresholds(), heartbeat=result, now=1_716_000_000.0)
    assert breaches == ()


def test_default_scenario_trips_reorg_block_age_and_latency() -> None:
    """The default knobs are tuned to force the rules engine to react."""
    result = sequencer_delay_heartbeat(now=1_716_000_000.0)
    breaches = evaluate(BreachThresholds(), heartbeat=result, now=1_716_000_000.0)
    rules = {b.rule for b in breaches}
    assert {"reorg_is_breach", "block_age_seconds_max", "rpc_latency_ms_max"} <= rules
