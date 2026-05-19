"""Append-only audit log with row-level HMAC tamper evidence.

Two layers of defence:

1. **Append-only triggers.** SQLite triggers raise on UPDATE or DELETE against
   the `audit_log` table. An operator running `UPDATE audit_log SET ...` from
   `sqlite3` will get an `ABORT` and no row changes.
2. **Row-level HMAC.** Each row carries an HMAC-SHA256 over
   `kind | recorded_at | payload`, keyed by `NAPG_AUDIT_HMAC_KEY` (an env-var
   kept distinct from any wallet key). If someone drops the triggers and
   tampers with row contents, `verify()` will detect the mismatch.

The HMAC key is never written to the DB. Loss of the key is recoverable
(verification stops working until rotation); leak of the key lets an attacker
re-sign tampered rows, so treat it as wallet-grade secret material.

A "decision" in the project brief maps to one or more rows here; the manifold
of row kinds (`breach`, eventually `decision`, `action`, `snapshot`) is open.
Add new kinds by writing through `record()` — the writer is schema-agnostic
beyond the JSON-serialisability of the payload.
"""

from __future__ import annotations

import hmac
import json
import sqlite3
import time
from collections.abc import Iterable, Iterator
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from napg.policy.breaches import Breach

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT    NOT NULL,
    recorded_at TEXT    NOT NULL,
    payload     TEXT    NOT NULL,
    hmac        TEXT    NOT NULL
);

CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
"""


class AuditRow(BaseModel):
    """One row read back from the audit log. `payload` is the parsed JSON."""

    model_config = ConfigDict(frozen=True)

    id: int
    kind: str
    recorded_at: str
    payload: dict[str, Any]
    hmac: str


class VerifyResult(BaseModel):
    """Outcome of `verify()`. `ok` is True only when every row checks out."""

    model_config = ConfigDict(frozen=True)

    total_rows: int
    tampered: tuple[int, ...]

    @property
    def ok(self) -> bool:
        return not self.tampered


def _canonical_bytes(kind: str, recorded_at: str, payload: str) -> bytes:
    return b"\x00".join(
        [kind.encode("utf-8"), recorded_at.encode("utf-8"), payload.encode("utf-8")]
    )


def _compute_hmac(key: bytes, kind: str, recorded_at: str, payload: str) -> str:
    return hmac.new(key, _canonical_bytes(kind, recorded_at, payload), sha256).hexdigest()


def _now_iso(at: float | None = None) -> str:
    moment = datetime.fromtimestamp(at if at is not None else time.time(), tz=timezone.utc)
    return moment.isoformat()


class AuditLog:
    """Open a connection to an append-only audit DB and write rows through it.

    Use as a context manager to guarantee the underlying connection closes.
    """

    def __init__(self, db_path: str | Path, hmac_key: str) -> None:
        if not hmac_key:
            raise ValueError(
                "audit log requires an HMAC key; set NAPG_AUDIT_HMAC_KEY before writing"
            )
        self._db_path = str(db_path)
        self._key = hmac_key.encode("utf-8")
        self._conn = sqlite3.connect(self._db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def __enter__(self) -> AuditLog:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def record(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        at: float | None = None,
    ) -> int:
        """Insert a single audit row. Returns the new row id."""
        recorded_at = _now_iso(at)
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = _compute_hmac(self._key, kind, recorded_at, payload_json)
        cur = self._conn.execute(
            "INSERT INTO audit_log (kind, recorded_at, payload, hmac) VALUES (?, ?, ?, ?)",
            (kind, recorded_at, payload_json, digest),
        )
        self._conn.commit()
        return int(cur.lastrowid or 0)

    def record_breaches(
        self,
        breaches: Iterable[Breach],
        *,
        at: float | None = None,
    ) -> tuple[int, ...]:
        """Insert N breach rows inside a single transaction.

        All-or-nothing semantics: any failure rolls back the whole set, so a
        decision cycle never leaves the log half-written.
        """
        breaches_list = list(breaches)
        if not breaches_list:
            return ()
        recorded_at = _now_iso(at)
        ids: list[int] = []
        with self._conn:
            for breach in breaches_list:
                payload_json = breach.model_dump_json()
                digest = _compute_hmac(self._key, "breach", recorded_at, payload_json)
                cur = self._conn.execute(
                    "INSERT INTO audit_log (kind, recorded_at, payload, hmac) VALUES (?, ?, ?, ?)",
                    ("breach", recorded_at, payload_json, digest),
                )
                ids.append(int(cur.lastrowid or 0))
        return tuple(ids)

    def iter_rows(self) -> Iterator[AuditRow]:
        """Yield every row in insertion order."""
        cursor = self._conn.execute(
            "SELECT id, kind, recorded_at, payload, hmac FROM audit_log ORDER BY id ASC"
        )
        for row in cursor:
            yield AuditRow(
                id=row[0],
                kind=row[1],
                recorded_at=row[2],
                payload=json.loads(row[3]),
                hmac=row[4],
            )


def verify(db_path: str | Path, hmac_key: str) -> VerifyResult:
    """Walk every audit row, recompute its HMAC, return mismatching row ids.

    Pure read-only — opens a fresh connection so it can run against a DB that
    a long-lived writer is also holding open.
    """
    if not hmac_key:
        raise ValueError("verify requires the audit HMAC key")
    key = hmac_key.encode("utf-8")
    tampered: list[int] = []
    total = 0
    with closing(sqlite3.connect(str(db_path))) as conn:
        cursor = conn.execute(
            "SELECT id, kind, recorded_at, payload, hmac FROM audit_log ORDER BY id ASC"
        )
        for row_id, kind, recorded_at, payload, stored in cursor:
            total += 1
            expected = _compute_hmac(key, kind, recorded_at, payload)
            if not hmac.compare_digest(expected, stored):
                tampered.append(int(row_id))
    return VerifyResult(total_rows=total, tampered=tuple(tampered))


__all__ = [
    "AuditLog",
    "AuditRow",
    "VerifyResult",
    "verify",
]
