"""Web3.py heartbeat against a Base RPC endpoint.

Reports latency, latest block, and reorg state. Reorgs are detected by checking
that each new block's `parent_hash` chains to the previous block we recorded at
`block.number - 1`. A mismatch means the chain reorganised between ticks.

Every RPC response is validated through a Pydantic model before being acted on:
treat upstream as hostile (per Phase 1 security checklist).
"""

from __future__ import annotations

import re
import time
from collections import deque
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from web3 import Web3

from napg.redact import redact_url

_HASH_RE = re.compile(r"^0x[0-9a-f]{64}$")


def _normalise_hash(value: Any) -> str:
    """Accept bytes, HexBytes, or str and return a lowercase 0x-prefixed 32-byte hex string."""
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    if isinstance(value, str):
        text = value.lower()
        if not text.startswith("0x"):
            text = "0x" + text
        return text
    raise ValueError(f"unsupported hash type: {type(value).__name__}")


class BlockSnapshot(BaseModel):
    """A validated view of a single block, derived from an RPC response."""

    model_config = ConfigDict(frozen=True)

    number: int = Field(ge=0)
    hash: str
    parent_hash: str
    timestamp: int = Field(ge=0)

    @field_validator("hash", "parent_hash", mode="before")
    @classmethod
    def _normalise(cls, value: Any) -> str:
        normalised = _normalise_hash(value)
        if not _HASH_RE.match(normalised):
            raise ValueError(f"not a 32-byte hex hash: {normalised!r}")
        return normalised

    @classmethod
    def from_rpc(cls, raw: Mapping[str, Any]) -> BlockSnapshot:
        return cls(
            number=raw["number"],
            hash=raw["hash"],
            parent_hash=raw["parentHash"],
            timestamp=raw["timestamp"],
        )


class HeartbeatResult(BaseModel):
    """One heartbeat tick: what we saw, how long it took, whether it chained.

    `rpc_url` is the redacted form (scheme + host only); the raw URL never
    enters this object, so the result is always safe to log or persist.
    """

    model_config = ConfigDict(frozen=True)

    rpc_url: str
    chain_id: int
    latency_ms: float = Field(ge=0)
    block: BlockSnapshot
    reorg_detected: bool
    observed_at: float


class RpcHeartbeat:
    """Single-provider heartbeat. Inject a `Web3` instance to mock in tests."""

    def __init__(
        self,
        rpc_url: str,
        web3: Web3 | None = None,
        history_size: int = 8,
    ) -> None:
        if not rpc_url.startswith("https://"):
            raise ValueError("RPC URL must use https://")
        self.rpc_url = rpc_url
        self._web3 = web3 if web3 is not None else Web3(Web3.HTTPProvider(rpc_url))
        self._history: deque[BlockSnapshot] = deque(maxlen=history_size)

    @property
    def history(self) -> tuple[BlockSnapshot, ...]:
        return tuple(self._history)

    def tick(self) -> HeartbeatResult:
        start = time.perf_counter()
        chain_id = self._web3.eth.chain_id
        raw_block = self._web3.eth.get_block("latest")
        latency_ms = (time.perf_counter() - start) * 1000.0

        block = BlockSnapshot.from_rpc(raw_block)
        reorg = self._detect_reorg(block)
        self._record(block)

        return HeartbeatResult(
            rpc_url=redact_url(self.rpc_url),
            chain_id=chain_id,
            latency_ms=latency_ms,
            block=block,
            reorg_detected=reorg,
            observed_at=time.time(),
        )

    def _detect_reorg(self, block: BlockSnapshot) -> bool:
        prior = self._find(block.number - 1)
        if prior is None:
            return False
        return prior.hash != block.parent_hash

    def _find(self, number: int) -> BlockSnapshot | None:
        for snap in self._history:
            if snap.number == number:
                return snap
        return None

    def _record(self, block: BlockSnapshot) -> None:
        existing = self._find(block.number)
        if existing is not None:
            self._history.remove(existing)
        self._history.append(block)
