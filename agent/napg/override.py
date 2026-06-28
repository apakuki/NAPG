"""Emergency migration override — breaking-glass, ruthlessly scoped.

Hardening decision 4 (see docs/runbooks/emergency-migration.md). When Tenderly
(AgentShield Stage 3) is unavailable, a correlated outage could block the very
`migrate_to_safe` rescue NAPG exists to perform. This override buys back *only*
that one rescue path when the deterministic sim gate is gone — and nothing else.

The design rule, non-negotiable: **emergency mode is not arbitrary-signing mode.**
Every constraint below is independent and fail-closed; all other AgentShield
stages (kill-switch, Intent Judge, Policy caps + denylist, Honeypot) still run.
The override substitutes for the Tenderly stage and for nothing else.

Constraints (all required):
1. Native transfer only — `data == "0x"`. No swaps, approvals, contract calls.
2. Destination is the pre-pinned allowlisted safe address. No dynamic, LLM-, or
   user-supplied destinations.
3. Amount stays under the Stage 2 caps (unchanged — Stage 2 still runs).
4. Manual approval — an override is *armed* by a human with a justification; it
   is never produced automatically from a detected event.
5. Mandatory audit — arming writes a `migration_override_armed` row (who / when /
   why / safe); execution writes the usual `validation` + `action` rows.
6. Expiry — an armed override lapses at `expires_at`; an emergency flag never
   becomes permanent.
7. Two-step activation — execution is refused until `executable_after` (arm +
   wait). The mechanism exists now so a future M-of-N quorum drops in unchanged.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from napg.agentshield.pipeline import StageResult, TxIntent
from napg.audit import AuditLog

_NATIVE_TRANSFER_CALLDATA = "0x"


class MigrationOverride(BaseModel):
    """An armed emergency override. Frozen once armed."""

    model_config = ConfigDict(frozen=True)

    safe_address: str
    approver: str
    justification: str
    armed_at: float
    executable_after: float  # armed_at + wait (two-step)
    expires_at: float  # armed_at + ttl


class OverrideViolation(RuntimeError):
    """Raised when an intent does not satisfy every override constraint."""


def arm_migration_override(
    audit_log: AuditLog,
    *,
    safe_address: str,
    approver: str,
    justification: str,
    now: float,
    wait_seconds: float,
    ttl_seconds: float,
) -> MigrationOverride:
    """Arm an override and record the mandatory `migration_override_armed` row.

    `approver` and `justification` are required by the caller (manual approval);
    an empty justification is refused — breaking glass must always say why.
    """
    if not approver or not justification:
        raise OverrideViolation("arming requires a non-empty approver and justification")
    if not safe_address.startswith("0x") or len(safe_address) != 42:
        raise OverrideViolation(f"safe_address is not a 20-byte 0x-hex address: {safe_address!r}")
    grant = MigrationOverride(
        safe_address=safe_address,
        approver=approver,
        justification=justification,
        armed_at=now,
        executable_after=now + wait_seconds,
        expires_at=now + ttl_seconds,
    )
    audit_log.record("migration_override_armed", grant.model_dump(mode="json"), at=now)
    return grant


def check_override(grant: MigrationOverride, intent: TxIntent, *, now: float) -> None:
    """Fail-closed: raise OverrideViolation unless every constraint holds."""
    if intent.action != "migrate_to_safe":
        raise OverrideViolation(f"override only covers migrate_to_safe, not {intent.action!r}")
    if intent.data != _NATIVE_TRANSFER_CALLDATA:
        raise OverrideViolation("override is native-transfer only (data must be 0x)")
    if intent.to_address.lower() != grant.safe_address.lower():
        raise OverrideViolation("override destination must be the armed safe address")
    if now < grant.executable_after:
        raise OverrideViolation("two-step wait has not elapsed; arm-then-wait before executing")
    if now > grant.expires_at:
        raise OverrideViolation("override has expired; re-arm to migrate")


def build_override_stage(grant: MigrationOverride, *, now: float):
    """A Stage 3 substitute that authorises only an override-valid migration.

    Slots into `validate_or_die(tenderly=...)` in the degraded path. Passing here
    means "Tenderly is bypassed because a human armed this exact rescue"; every
    other stage still runs.
    """

    def _stage(intent: TxIntent) -> StageResult:
        try:
            check_override(grant, intent, now=now)
        except OverrideViolation as exc:
            return StageResult(stage="tenderly", passed=False, reason=f"override denied: {exc}")
        return StageResult(
            stage="tenderly",
            passed=True,
            reason="migration override: Tenderly bypassed; human-armed rescue",
            details={
                "override": True,
                "approver": grant.approver,
                "armed_at": grant.armed_at,
                "expires_at": grant.expires_at,
            },
        )

    return _stage


def latest_armed_override(audit_log: AuditLog) -> MigrationOverride | None:
    """Return the most recently armed override, or None. The `execute` step reads
    this, then re-checks the two-step wait + expiry at execution time."""
    rows = audit_log.query(kind="migration_override_armed", limit=1, newest_first=True)
    if not rows:
        return None
    return MigrationOverride.model_validate(rows[0].payload)


__all__ = [
    "MigrationOverride",
    "OverrideViolation",
    "arm_migration_override",
    "build_override_stage",
    "check_override",
    "latest_armed_override",
]
