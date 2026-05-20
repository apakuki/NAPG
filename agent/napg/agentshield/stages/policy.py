"""Stage 2 — Policy Validation.

Five fail-closed checks, evaluated in order until one fails:

1. Destination is not on the denylist (lowercased exact match).
2. Destination is on the allowlist when the allowlist is non-empty.
3. Value is at or below `max_value_wei_per_tx`.
4. Calldata is empty (native transfer only) until ERC-20 decoding lands.
5. Projected daily spend (sum of non-dry-run `action` rows in the last
   24h plus this tx) is at or below `daily_spend_cap_wei`.

Stage 2 is the only stage that reads the audit log (for daily-spend
accounting). The audit-log argument is optional so unit tests can run
against an in-memory policy without standing up SQLite.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone

from napg.agentshield.pipeline import StageResult, TxIntent
from napg.agentshield.policy import Denylist, PolicyConfig
from napg.audit import AuditLog

_NATIVE_TRANSFER_CALLDATA = "0x"
_DAILY_WINDOW_SECONDS = 24 * 60 * 60


def build_policy_stage(
    *,
    policy: PolicyConfig,
    denylist: Denylist,
    audit_log: AuditLog | None = None,
    now_provider: Callable[[], float] | None = None,
) -> Callable[[TxIntent], StageResult]:
    """Return a Stage 2 callable bound to this policy + denylist.

    `audit_log` is optional: without it, the daily-spend ceiling check is
    skipped (e.g. for fast unit tests). With it, recent non-dry-run
    `action` rows are summed against `policy.daily_spend_cap_wei`.

    `now_provider` is injectable for time-freezing tests; defaults to
    `time.time`.
    """
    now_fn = now_provider or time.time

    def _stage(intent: TxIntent) -> StageResult:
        to = intent.to_address.lower()
        if denylist.contains(to):
            return StageResult(
                stage="policy", passed=False, reason=f"destination on denylist: {to}"
            )

        if policy.destination_allowlist and to not in policy.destination_allowlist:
            return StageResult(
                stage="policy",
                passed=False,
                reason=f"destination not on allowlist: {to}",
            )

        if intent.value_wei > policy.max_value_wei_per_tx:
            return StageResult(
                stage="policy",
                passed=False,
                reason=(
                    f"value_wei {intent.value_wei} exceeds per-tx cap {policy.max_value_wei_per_tx}"
                ),
            )

        if intent.data != _NATIVE_TRANSFER_CALLDATA:
            # ERC-20 calldata decoding lands later in Phase 2 or Phase 5; until
            # then any non-native call is fail-closed regardless of token_allowlist.
            return StageResult(
                stage="policy",
                passed=False,
                reason="non-native calldata blocked (ERC-20 decoding not yet implemented)",
            )

        if audit_log is not None:
            spend_so_far = _daily_spend_wei(audit_log, now_fn())
            projected = spend_so_far + intent.value_wei
            if projected > policy.daily_spend_cap_wei:
                return StageResult(
                    stage="policy",
                    passed=False,
                    reason=(
                        f"projected daily spend {projected} exceeds cap "
                        f"{policy.daily_spend_cap_wei}"
                    ),
                )

        return StageResult(stage="policy", passed=True)

    return _stage


def _daily_spend_wei(audit_log: AuditLog, now: float) -> int:
    """Sum non-dry-run `action` rows recorded in the trailing 24h."""
    cutoff = datetime.fromtimestamp(now - _DAILY_WINDOW_SECONDS, tz=timezone.utc).isoformat()
    total = 0
    for row in audit_log.iter_rows():
        if row.kind != "action":
            continue
        if row.recorded_at < cutoff:
            continue
        payload = row.payload
        if payload.get("dry_run"):
            continue
        value_wei = payload.get("value_wei")
        if isinstance(value_wei, int):
            total += value_wei
    return total


__all__ = ["build_policy_stage"]
