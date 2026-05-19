"""Unit tests for napg.audit — append-only writes, HMAC tamper-evidence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from napg.audit import AuditLog, verify
from napg.policy.breaches import Breach


def _breach(rule: str = "rpc_latency_ms_max", actual: int = 5_000) -> Breach:
    return Breach(
        rule=rule,
        source="heartbeat",
        threshold=2_000,
        actual=actual,
        message=f"RPC latency {actual}ms exceeds threshold",
        detected_at=1_716_000_010.0,
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "audit.db"


KEY = "test-hmac-key-do-not-use-in-prod"


def test_requires_hmac_key(db_path: Path) -> None:
    with pytest.raises(ValueError, match="HMAC key"):
        AuditLog(db_path, hmac_key="")


def test_record_single_row_and_read_back(db_path: Path) -> None:
    with AuditLog(db_path, hmac_key=KEY) as log:
        row_id = log.record("snapshot", {"foo": "bar", "n": 42}, at=1_716_000_010.0)
        rows = list(log.iter_rows())

    assert row_id == 1
    assert len(rows) == 1
    assert rows[0].kind == "snapshot"
    assert rows[0].payload == {"foo": "bar", "n": 42}
    assert rows[0].hmac  # non-empty
    assert "T" in rows[0].recorded_at  # ISO 8601


def test_record_breaches_writes_one_row_each(db_path: Path) -> None:
    with AuditLog(db_path, hmac_key=KEY) as log:
        ids = log.record_breaches([_breach(actual=5_000), _breach(actual=3_500)])
        rows = list(log.iter_rows())

    assert ids == (1, 2)
    assert len(rows) == 2
    assert all(r.kind == "breach" for r in rows)
    assert rows[0].payload["actual"] == 5_000
    assert rows[1].payload["actual"] == 3_500


def test_record_breaches_empty_is_a_no_op(db_path: Path) -> None:
    with AuditLog(db_path, hmac_key=KEY) as log:
        assert log.record_breaches([]) == ()
        assert list(log.iter_rows()) == []


def test_verify_clean_log_reports_ok(db_path: Path) -> None:
    with AuditLog(db_path, hmac_key=KEY) as log:
        log.record_breaches([_breach(), _breach(actual=4_000)])

    result = verify(db_path, KEY)
    assert result.total_rows == 2
    assert result.tampered == ()
    assert result.ok is True


def test_verify_detects_tamper_after_triggers_dropped(db_path: Path) -> None:
    with AuditLog(db_path, hmac_key=KEY) as log:
        log.record_breaches([_breach(), _breach(actual=4_000)])

    # Simulate an attacker: drop the append-only triggers and tamper.
    with sqlite3.connect(db_path) as conn:
        conn.executescript("DROP TRIGGER audit_log_no_update;")
        conn.execute(
            "UPDATE audit_log SET payload = ? WHERE id = 1",
            (
                '{"rule":"forged","source":"x","severity":"warn","threshold":0,"actual":0,"message":"x","detected_at":0}',
            ),
        )
        conn.commit()

    result = verify(db_path, KEY)
    assert result.total_rows == 2
    assert result.tampered == (1,)
    assert result.ok is False


def test_update_blocked_by_trigger(db_path: Path) -> None:
    with AuditLog(db_path, hmac_key=KEY) as log:
        log.record_breaches([_breach()])

    with (
        sqlite3.connect(db_path) as conn,
        pytest.raises(sqlite3.IntegrityError, match="append-only"),
    ):
        conn.execute("UPDATE audit_log SET payload = ? WHERE id = 1", ("tampered",))
        conn.commit()


def test_delete_blocked_by_trigger(db_path: Path) -> None:
    with AuditLog(db_path, hmac_key=KEY) as log:
        log.record_breaches([_breach()])

    with (
        sqlite3.connect(db_path) as conn,
        pytest.raises(sqlite3.IntegrityError, match="append-only"),
    ):
        conn.execute("DELETE FROM audit_log WHERE id = 1")
        conn.commit()


def test_wrong_hmac_key_treats_every_row_as_tampered(db_path: Path) -> None:
    with AuditLog(db_path, hmac_key=KEY) as log:
        log.record_breaches([_breach(), _breach(actual=4_000)])

    result = verify(db_path, "completely-different-key")
    assert result.tampered == (1, 2)
    assert result.ok is False


def test_schema_idempotent_on_reopen(db_path: Path) -> None:
    """Reopening the same DB must not error on the CREATE TABLE/TRIGGER statements."""
    with AuditLog(db_path, hmac_key=KEY) as log:
        log.record("snapshot", {"first": True})

    with AuditLog(db_path, hmac_key=KEY) as log:
        log.record("snapshot", {"second": True})
        rows = list(log.iter_rows())

    assert [r.payload for r in rows] == [{"first": True}, {"second": True}]


def test_hmac_key_never_stored_in_db(db_path: Path) -> None:
    """Sanity: the HMAC key string never lands in the SQLite file."""
    secret = "do-not-leak-this-secret-key-please"
    with AuditLog(db_path, hmac_key=secret) as log:
        log.record_breaches([_breach()])

    blob = db_path.read_bytes()
    assert secret.encode("utf-8") not in blob


def test_verify_requires_key(db_path: Path) -> None:
    with AuditLog(db_path, hmac_key=KEY) as log:
        log.record_breaches([_breach()])

    with pytest.raises(ValueError, match="HMAC key"):
        verify(db_path, hmac_key="")
