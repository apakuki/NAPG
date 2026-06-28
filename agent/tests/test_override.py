"""Tests for napg.override — emergency migration override (breaking-glass)."""

from __future__ import annotations

import pytest

from napg.agentshield.pipeline import TxIntent
from napg.audit import AuditLog
from napg.override import (
    MigrationOverride,
    OverrideViolation,
    arm_migration_override,
    build_override_stage,
    check_override,
    latest_armed_override,
)

_HMAC_KEY = "test-audit-hmac-key"
SAFE = "0x" + "5a" * 20
AGENT = "0x" + "a9" * 20


def _grant(
    *, armed_at: float = 1000.0, wait: float = 60.0, ttl: float = 1800.0
) -> MigrationOverride:
    return MigrationOverride(
        safe_address=SAFE,
        approver="sam",
        justification="tenderly down during depeg",
        armed_at=armed_at,
        executable_after=armed_at + wait,
        expires_at=armed_at + ttl,
    )


def _migrate_intent(
    *, to: str = SAFE, data: str = "0x", action: str = "migrate_to_safe"
) -> TxIntent:
    return TxIntent(
        action=action,
        from_address=AGENT,
        to_address=to,
        value_wei=1000,
        data=data,
    )


# --- arming (manual approval + mandatory audit) -----------------------------


def test_arm_requires_approver_and_justification(tmp_path):
    with AuditLog(tmp_path / "audit.db", _HMAC_KEY) as log:
        with pytest.raises(OverrideViolation, match="approver and justification"):
            arm_migration_override(
                log,
                safe_address=SAFE,
                approver="",
                justification="x",
                now=1.0,
                wait_seconds=60,
                ttl_seconds=1800,
            )
        with pytest.raises(OverrideViolation, match="approver and justification"):
            arm_migration_override(
                log,
                safe_address=SAFE,
                approver="sam",
                justification="",
                now=1.0,
                wait_seconds=60,
                ttl_seconds=1800,
            )


def test_arm_rejects_bad_safe_address(tmp_path):
    with (
        AuditLog(tmp_path / "audit.db", _HMAC_KEY) as log,
        pytest.raises(OverrideViolation, match="0x-hex address"),
    ):
        arm_migration_override(
            log,
            safe_address="0xnope",
            approver="sam",
            justification="why",
            now=1.0,
            wait_seconds=60,
            ttl_seconds=1800,
        )


def test_arm_records_audit_row_and_sets_windows(tmp_path):
    with AuditLog(tmp_path / "audit.db", _HMAC_KEY) as log:
        grant = arm_migration_override(
            log,
            safe_address=SAFE,
            approver="sam",
            justification="depeg",
            now=1000.0,
            wait_seconds=60,
            ttl_seconds=1800,
        )
        rows = log.query(kind="migration_override_armed", limit=10)
    assert grant.executable_after == 1060.0
    assert grant.expires_at == 2800.0
    assert len(rows) == 1
    assert rows[0].payload["approver"] == "sam"
    assert rows[0].payload["justification"] == "depeg"


# --- check_override: every constraint is fail-closed ------------------------


def test_check_passes_valid_migration_in_window():
    grant = _grant()
    check_override(grant, _migrate_intent(), now=1100.0)  # after wait, before expiry


def test_check_rejects_non_migrate_action():
    with pytest.raises(OverrideViolation, match="only covers migrate_to_safe"):
        check_override(_grant(), _migrate_intent(action="swap"), now=1100.0)


def test_check_rejects_non_native_calldata():
    with pytest.raises(OverrideViolation, match="native-transfer only"):
        check_override(_grant(), _migrate_intent(data="0xdeadbeef"), now=1100.0)


def test_check_rejects_wrong_destination():
    other = "0x" + "ee" * 20
    with pytest.raises(OverrideViolation, match="armed safe address"):
        check_override(_grant(), _migrate_intent(to=other), now=1100.0)


def test_check_rejects_before_two_step_wait():
    grant = _grant(armed_at=1000.0, wait=60.0)
    with pytest.raises(OverrideViolation, match="two-step wait"):
        check_override(grant, _migrate_intent(), now=1030.0)  # only 30s after arm


def test_check_rejects_after_expiry():
    grant = _grant(armed_at=1000.0, ttl=1800.0)
    with pytest.raises(OverrideViolation, match="expired"):
        check_override(grant, _migrate_intent(), now=3000.0)


# --- the Stage 3 substitute -------------------------------------------------


def test_override_stage_passes_valid_migration():
    stage = build_override_stage(_grant(), now=1100.0)
    result = stage(_migrate_intent())
    assert result.passed is True
    assert result.details["override"] is True
    assert result.details["approver"] == "sam"


def test_override_stage_denies_invalid():
    stage = build_override_stage(_grant(), now=1100.0)
    result = stage(_migrate_intent(data="0xdeadbeef"))
    assert result.passed is False
    assert "override denied" in result.reason


# --- two-step execution reads the armed grant -------------------------------


def test_override_validator_builds_without_tenderly_creds():
    """The whole point: the override validator must construct when Tenderly is
    unavailable (no creds). Other stages (incl. the Intent Judge) still apply;
    we build it but do not invoke (that would call Anthropic)."""
    from napg.agentshield.production import build_migration_override_validator
    from napg.config import Settings

    settings = Settings(_env_file=None, ANTHROPIC_API_KEY="test-key")  # type: ignore[call-arg]
    validator = build_migration_override_validator(settings, grant=_grant(), now=1100.0)
    assert callable(validator)


def test_latest_armed_override_roundtrip(tmp_path):
    with AuditLog(tmp_path / "audit.db", _HMAC_KEY) as log:
        assert latest_armed_override(log) is None
        arm_migration_override(
            log,
            safe_address=SAFE,
            approver="sam",
            justification="depeg",
            now=1000.0,
            wait_seconds=60,
            ttl_seconds=1800,
        )
        grant = latest_armed_override(log)
    assert grant is not None
    assert grant.safe_address == SAFE
    assert grant.executable_after == 1060.0
