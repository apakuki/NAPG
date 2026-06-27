"""Guardian Mode entitlements.

Phase 4 Group D. Guardian Mode is the B2C subscription where NAPG monitors a
specific user's lending / LP positions. This module is the entitlement layer:
who is currently entitled, decided *only* from the append-only audit log.

The security property (manual test 4.9): entitlement is never read from a client
claim. The status check reads `entitlement` rows from the tamper-evident audit
log and nothing else, so a forged `x-entitled` header or request body cannot
grant access. Granting an entitlement writes one `entitlement` row; the eventual
billing path (an x402 subscription payment) calls `grant_entitlement`, but the
billing UI itself is out of scope for this scaffolding.

Entitlements are keyed by Farcaster `fid` (the identity SIWF establishes). A
renewal is just another `entitlement` row; the active window is the latest
`expires_at` across a fid's grants.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from napg.audit import AuditLog

DEFAULT_PLAN = "guardian-monthly"


class EntitlementGrant(BaseModel):
    """One Guardian Mode entitlement grant. JSON-safe, audit-log-ready."""

    model_config = ConfigDict(frozen=True)

    fid: int = Field(ge=0)
    plan: str
    granted_at: float
    expires_at: float


class GuardianStatus(BaseModel):
    """The current entitlement state for a fid, derived from the audit log."""

    model_config = ConfigDict(frozen=True)

    fid: int
    entitled: bool
    plan: str | None = None
    expires_at: float | None = None


def grant_entitlement(
    audit_log: AuditLog,
    *,
    fid: int,
    granted_at: float,
    duration_seconds: float,
    plan: str = DEFAULT_PLAN,
) -> EntitlementGrant:
    """Record a Guardian Mode entitlement for `fid` and return the grant.

    Writes one `entitlement` row to the append-only audit log. Called by the
    subscription/payment path once it lands; tests call it directly to seed.
    """
    grant = EntitlementGrant(
        fid=fid,
        plan=plan,
        granted_at=granted_at,
        expires_at=granted_at + duration_seconds,
    )
    audit_log.record("entitlement", grant.model_dump(mode="json"), at=granted_at)
    return grant


def entitlement_status(audit_log: AuditLog, fid: int, *, now: float) -> GuardianStatus:
    """Decide `fid`'s entitlement from the audit log alone.

    Reads every `entitlement` row for the fid and reports the grant with the
    furthest-out `expires_at`. Entitled iff that window has not lapsed at `now`.
    Source of truth is the log, never any client-supplied claim.
    """
    best: EntitlementGrant | None = None
    for row in audit_log.query(kind="entitlement", limit=500, newest_first=True):
        if row.payload.get("fid") != fid:
            continue
        grant = EntitlementGrant.model_validate(row.payload)
        if best is None or grant.expires_at > best.expires_at:
            best = grant

    if best is None or best.expires_at <= now:
        return GuardianStatus(fid=fid, entitled=False)
    return GuardianStatus(fid=fid, entitled=True, plan=best.plan, expires_at=best.expires_at)


__all__ = [
    "DEFAULT_PLAN",
    "EntitlementGrant",
    "GuardianStatus",
    "entitlement_status",
    "grant_entitlement",
]
