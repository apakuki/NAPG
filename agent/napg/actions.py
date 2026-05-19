"""Onchain actions the agent can take, with audit-log integration.

Phase 1 ships one action: `migrate_to_safe`, a native-ETH transfer from the
CDP-managed agent wallet to a pre-defined safe address. Phase 2 will wrap
every action below in AgentShield's 4-stage validation pipeline (Intent
Judge → Policy → Tenderly Simulation → Honeypot Detection) before any tx
reaches the wallet; this commit deliberately leaves a hard seam between
"decide" and "execute" so that pipeline drops in cleanly later.

The audit-log integration writes one `action` row per call. Dry-run calls
are recorded with `dry_run=True` and no tx_hash; live calls are recorded
after the receipt is observed so the row contains the block number and
final status.
"""

from __future__ import annotations

import json
import time
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from napg.audit import AuditLog


class _WalletLike(Protocol):
    """Narrow interface the actions module needs from a wallet provider.

    Decoupling from `CdpEvmWalletProvider` keeps tests injectable without
    spinning up the SDK and keeps the seam explicit for Phase 2 hardening.
    """

    def get_address(self) -> str: ...
    def native_transfer(self, to: str, value: str) -> str: ...
    def wait_for_transaction_receipt(self, tx_hash: str) -> Any: ...


class ActionRecord(BaseModel):
    """Audit-log-ready record of one action. JSON-safe across the board."""

    model_config = ConfigDict(frozen=True)

    action: str
    dry_run: bool
    from_address: str
    to_address: str
    value_wei: int = Field(ge=0)
    tx_hash: str | None = None
    block_number: int | None = None
    status: str | None = None
    observed_at: float


def migrate_to_safe(
    wallet: _WalletLike,
    safe_address: str,
    value_wei: int,
    *,
    dry_run: bool = True,
    audit_log: AuditLog | None = None,
) -> ActionRecord:
    """Move `value_wei` of native ETH from the agent wallet to `safe_address`.

    `dry_run=True` is the default. The caller (substep 9 integration) flips
    it explicitly when a real migration is authorised.

    Returns an `ActionRecord` describing what happened. When `audit_log` is
    provided, the same record is appended to the audit DB as an `action`
    row. Append-only: any retry creates a new row rather than mutating one.
    """
    if value_wei < 0:
        raise ValueError("value_wei must be non-negative")
    if not safe_address.startswith("0x") or len(safe_address) != 42:
        raise ValueError(f"safe_address is not a 20-byte 0x-hex address: {safe_address!r}")

    from_address = wallet.get_address()

    if dry_run:
        record = ActionRecord(
            action="migrate_to_safe",
            dry_run=True,
            from_address=from_address,
            to_address=safe_address,
            value_wei=value_wei,
            observed_at=time.time(),
        )
    else:
        tx_hash = wallet.native_transfer(to=safe_address, value=str(value_wei))
        receipt = wallet.wait_for_transaction_receipt(tx_hash)
        block_number = _extract_block_number(receipt)
        status = _extract_status(receipt)
        record = ActionRecord(
            action="migrate_to_safe",
            dry_run=False,
            from_address=from_address,
            to_address=safe_address,
            value_wei=value_wei,
            tx_hash=tx_hash,
            block_number=block_number,
            status=status,
            observed_at=time.time(),
        )

    if audit_log is not None:
        audit_log.record("action", json.loads(record.model_dump_json()))

    return record


def _extract_block_number(receipt: Any) -> int | None:
    for attr in ("block_number", "blockNumber"):
        value = getattr(receipt, attr, None)
        if value is not None:
            return int(value)
    return None


def _extract_status(receipt: Any) -> str | None:
    raw = getattr(receipt, "status", None)
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    return "success" if int(raw) == 1 else "failure"


__all__ = ["ActionRecord", "migrate_to_safe"]
