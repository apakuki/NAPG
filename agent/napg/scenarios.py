"""Synthetic monitor outputs for exercising the pipeline without live infra.

Phase 1 ships one scenario: `sequencer_delay_heartbeat`, which mimics what
NAPG would see during a Base sequencer outage — no fresh blocks for N
seconds, then recovery with a reorg as the chain re-sequences. The pair of
signals (stale block + reorg) reliably maps to `migrate_to_safe` in the
reasoning matrix (reorg alone is rule 2), so it is the right shape for the
"agent detects sequencer delay and migrates testnet funds" milestone.

Synthetic outputs are deliberately produced as `HeartbeatResult` instances
rather than mocked `Web3` providers. The orchestrator is probe-agnostic; it
only needs the already-collected result. That keeps the simulation path
narrow: one pure function, no transport mocking, no network indirection.
"""

from __future__ import annotations

import time

from napg.monitor.rpc import BlockSnapshot, HeartbeatResult

BASE_SEPOLIA_CHAIN_ID = 84532
SYNTHETIC_RPC_URL = "https://synthetic.scenario/<redacted>"

_HASH_DELAYED = "0x" + "d1" * 32
_HASH_DELAYED_PARENT = "0x" + "d0" * 32


def sequencer_delay_heartbeat(
    *,
    stale_seconds: int = 600,
    include_reorg: bool = True,
    chain_id: int = BASE_SEPOLIA_CHAIN_ID,
    rpc_url: str = SYNTHETIC_RPC_URL,
    latency_ms: float = 4500.0,
    block_number: int = 1,
    now: float | None = None,
) -> HeartbeatResult:
    """Build a `HeartbeatResult` consistent with a sequencer outage.

    Defaults are tuned to trip the rules engine: 600 s stale block (block-age
    threshold is 30 s), 4500 ms latency (latency threshold is 2000 ms), and a
    reorg flag. The reorg is the load-bearing signal for the reasoning
    matrix — it forces `migrate_to_safe` regardless of the other breaches.

    `now` is injectable so the caller can produce deterministic timestamps
    in tests. The block timestamp is always `now - stale_seconds`.
    """
    if stale_seconds < 0:
        raise ValueError("stale_seconds must be non-negative")
    if latency_ms < 0:
        raise ValueError("latency_ms must be non-negative")
    observed_at = now if now is not None else time.time()
    block_timestamp = int(observed_at) - stale_seconds

    block = BlockSnapshot(
        number=block_number,
        hash=_HASH_DELAYED,
        parent_hash=_HASH_DELAYED_PARENT,
        timestamp=max(block_timestamp, 0),
    )
    return HeartbeatResult(
        rpc_url=rpc_url,
        chain_id=chain_id,
        latency_ms=latency_ms,
        block=block,
        reorg_detected=include_reorg,
        observed_at=observed_at,
    )


__all__ = [
    "BASE_SEPOLIA_CHAIN_ID",
    "SYNTHETIC_RPC_URL",
    "sequencer_delay_heartbeat",
]
