"""Tests for napg.guardian — Guardian Mode entitlements from the audit log."""

from __future__ import annotations

from napg.audit import AuditLog
from napg.guardian import entitlement_status, grant_entitlement

_HMAC_KEY = "test-audit-hmac-key"
_DAY = 86_400.0


def test_no_record_is_not_entitled(tmp_path):
    with AuditLog(tmp_path / "audit.db", _HMAC_KEY) as log:
        status = entitlement_status(log, 123, now=1000.0)
    assert status.entitled is False
    assert status.plan is None
    assert status.expires_at is None


def test_active_grant_is_entitled(tmp_path):
    with AuditLog(tmp_path / "audit.db", _HMAC_KEY) as log:
        grant = grant_entitlement(log, fid=123, granted_at=1000.0, duration_seconds=30 * _DAY)
        status = entitlement_status(log, 123, now=1000.0 + _DAY)
    assert status.entitled is True
    assert status.plan == "guardian-monthly"
    assert status.expires_at == grant.expires_at


def test_expired_grant_is_not_entitled(tmp_path):
    with AuditLog(tmp_path / "audit.db", _HMAC_KEY) as log:
        grant_entitlement(log, fid=123, granted_at=1000.0, duration_seconds=_DAY)
        status = entitlement_status(log, 123, now=1000.0 + 2 * _DAY)
    assert status.entitled is False


def test_renewal_uses_furthest_expiry(tmp_path):
    with AuditLog(tmp_path / "audit.db", _HMAC_KEY) as log:
        grant_entitlement(log, fid=123, granted_at=1000.0, duration_seconds=_DAY)
        renewal = grant_entitlement(log, fid=123, granted_at=1000.0, duration_seconds=60 * _DAY)
        # An earlier-expiring grant recorded after the renewal must not shadow it.
        grant_entitlement(log, fid=123, granted_at=1000.0, duration_seconds=2 * _DAY)
        status = entitlement_status(log, 123, now=1000.0 + 30 * _DAY)
    assert status.entitled is True
    assert status.expires_at == renewal.expires_at


def test_entitlement_is_per_fid(tmp_path):
    with AuditLog(tmp_path / "audit.db", _HMAC_KEY) as log:
        grant_entitlement(log, fid=123, granted_at=1000.0, duration_seconds=30 * _DAY)
        other = entitlement_status(log, 999, now=1000.0 + _DAY)
        owner = entitlement_status(log, 123, now=1000.0 + _DAY)
    assert other.entitled is False
    assert owner.entitled is True


def test_grant_writes_one_entitlement_row(tmp_path):
    with AuditLog(tmp_path / "audit.db", _HMAC_KEY) as log:
        grant_entitlement(log, fid=123, granted_at=1000.0, duration_seconds=_DAY)
        rows = log.query(kind="entitlement", limit=10)
    assert len(rows) == 1
    assert rows[0].payload["fid"] == 123
