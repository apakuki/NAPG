"""Onchain actions the agent can take, with audit-log integration.

Phase 1 shipped one action: `migrate_to_safe`, a native-ETH transfer from
the CDP-managed agent wallet to a pre-defined safe address. Phase 2 wraps
every signing call in AgentShield's 4-stage validation pipeline (Intent
Judge → Policy → Tenderly Simulation → Honeypot Detection). The wiring
lives behind the `validator` callable argument: callers (the CLI, the
orchestrator) build the live validator via
`napg.agentshield.production.build_production_validator(settings)` and
pass it in. Dry-run calls do not validate (they do not sign); live calls
must supply a validator and will raise `ValidationFailure` before any
wallet method is touched if any stage fails closed.

The audit-log integration writes one `action` row per call. Dry-run calls
are recorded with `dry_run=True` and no tx_hash; live calls are recorded
after the receipt is observed so the row contains the block number and
final status. The validator emits its own `validation` row independently
(see `napg.agentshield.pipeline`), so a failed validation still leaves a
forensic trace even though no `action` row lands.

`napg.actions` is one of the two production modules permitted to call
wallet signing methods (the other is `napg.agentshield`); the CI grep
test in `tests/test_codebase_invariants.py` fails the build if any other
module calls them directly.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from napg.agentshield.pipeline import TxIntent, ValidationResult
from napg.audit import AuditLog

WEI_PER_ETH = Decimal(10) ** 18


class _WalletLike(Protocol):
    """Narrow interface the actions module needs from a wallet provider.

    Decoupling from `CdpEvmWalletProvider` keeps tests injectable without
    spinning up the SDK and keeps the seam explicit for Phase 2 hardening.
    `value` is a whole-ether Decimal to match `CdpEvmWalletProvider.native_transfer`,
    which converts via `Web3.to_wei(value, "ether")` internally.
    """

    def get_address(self) -> str: ...
    def native_transfer(self, to: str, value: Decimal) -> str: ...
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


Validator = Callable[[TxIntent], ValidationResult]


def migrate_to_safe(
    wallet: _WalletLike,
    safe_address: str,
    value_wei: int,
    *,
    dry_run: bool = True,
    audit_log: AuditLog | None = None,
    validator: Validator | None = None,
    rationale: str = "",
    supporting_breaches: tuple[str, ...] = (),
) -> ActionRecord:
    """Move `value_wei` of native ETH from the agent wallet to `safe_address`.

    `dry_run=True` is the default. Non-dry-run calls require a `validator`:
    AgentShield's `validate_or_die` runs before any wallet method is touched
    and raises `ValidationFailure` on any stage failure or engaged kill-switch.

    `rationale` and `supporting_breaches` come from the upstream `Decision`
    (when called from the orchestrator) or describe the operator's reason
    (when called from the CLI). Both feed into the Intent Judge stage and
    are echoed back in the audit log.

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
        if validator is None:
            raise RuntimeError(
                "non-dry-run migrate_to_safe requires a validator (use "
                "napg.agentshield.production.build_production_validator)"
            )
        intent = TxIntent(
            action="migrate_to_safe",
            from_address=from_address,
            to_address=safe_address,
            value_wei=value_wei,
            data="0x",
            rationale=rationale,
            supporting_breaches=supporting_breaches,
        )
        # Raises ValidationFailure if any stage fails closed; the validation
        # row already landed in the audit log inside validate_or_die.
        validator(intent)

        # CdpEvmWalletProvider.native_transfer expects `value` in whole ether,
        # not wei — it runs `Web3.to_wei(value, "ether")` internally. Passing
        # wei here causes the CDP API to read it as 10^18-times-too-much and
        # reject as "Insufficient balance" regardless of the wallet balance.
        value_eth = Decimal(value_wei) / WEI_PER_ETH
        tx_hash = wallet.native_transfer(to=safe_address, value=value_eth)
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
