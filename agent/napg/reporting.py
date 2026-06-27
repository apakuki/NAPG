"""Assurance Report: a signed, audit-backed view over the breach record.

Phase 4 Group A. An Assurance Report is what a paying client agent (via x402)
or a Guardian Mode subscriber receives: a statement of what NAPG observed for a
protocol over a window, the breaches it recorded, a recommendation, and a
signature a consumer can verify independently.

Two deliberate choices:

1. **Ed25519 detached signature, not the operational wallet key.** The report is
   signed by a dedicated reporting key loaded from `NAPG_REPORTING_SIGNING_KEY`
   (a 32-byte seed, hex-encoded). It is structurally a different curve from the
   secp256k1 CDP MPC wallet, so a report signature can never be confused with,
   or substituted for, an on-chain transaction signature. The private seed is
   never written to the audit DB or into any report; only the signature and the
   key id (`kid`) travel with the report.
2. **The report is a view over the audit log.** Breaches come from the existing
   append-only audit log (`AuditLog.query`), not recomputed, so a report cannot
   claim a breach the tamper-evident log does not also hold. Every issued report
   writes a `report` row back to the log.

The `kid` is derived from the public key, so rotating the key changes the `kid`
and old reports still verify against the old published key.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, ConfigDict

from napg.audit import AuditLog
from napg.policy.breaches import Breach

_SEED_LEN = 32
_KID_LEN = 16


class ReportWindow(BaseModel):
    """The closed time interval a report covers, as POSIX timestamps."""

    model_config = ConfigDict(frozen=True)

    start_ts: float
    end_ts: float


class AssuranceReport(BaseModel):
    """A signed assurance statement. JSON-safe and audit-log-ready."""

    model_config = ConfigDict(frozen=True)

    protocol: str
    window: ReportWindow
    breaches: tuple[Breach, ...]
    recommendation: str
    generated_at: float
    kid: str
    signature: str

    def signing_bytes(self) -> bytes:
        """Canonical bytes the signature covers: every field except `signature`.

        Deterministic (sorted keys, compact separators) so signer and verifier
        agree byte-for-byte regardless of field order or whitespace.
        """
        payload = self.model_dump(mode="json", exclude={"signature"})
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def kid_for_public_key(public_key: Ed25519PublicKey) -> str:
    """Stable key id: the first 16 hex chars of sha256(raw public key)."""
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return sha256(raw).hexdigest()[:_KID_LEN]


class ReportSigner:
    """Holds the dedicated reporting key and signs Assurance Reports.

    Build from the configured seed (`from_settings`) in production, or from a
    raw key in tests. The private seed never leaves this object.
    """

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._private_key = private_key
        self._public_key = private_key.public_key()
        self.kid = kid_for_public_key(self._public_key)

    @classmethod
    def from_seed_hex(cls, seed_hex: str) -> ReportSigner:
        seed = bytes.fromhex(seed_hex.strip())
        if len(seed) != _SEED_LEN:
            raise ValueError(
                f"reporting signing key must be a {_SEED_LEN}-byte hex seed, got {len(seed)} bytes"
            )
        return cls(Ed25519PrivateKey.from_private_bytes(seed))

    @classmethod
    def from_settings(cls, settings: object) -> ReportSigner:
        seed_hex = getattr(settings, "reporting_signing_key", None)
        if not seed_hex:
            raise RuntimeError(
                "No reporting key configured. Set NAPG_REPORTING_SIGNING_KEY "
                "(generate one with `napg report generate-key`)."
            )
        return cls.from_seed_hex(seed_hex)

    def public_pem(self) -> bytes:
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def sign(
        self,
        *,
        protocol: str,
        window: ReportWindow,
        breaches: tuple[Breach, ...],
        recommendation: str,
        generated_at: float,
    ) -> AssuranceReport:
        """Build and sign an Assurance Report with this key's `kid`."""
        unsigned = AssuranceReport(
            protocol=protocol,
            window=window,
            breaches=breaches,
            recommendation=recommendation,
            generated_at=generated_at,
            kid=self.kid,
            signature="",
        )
        signature = self._private_key.sign(unsigned.signing_bytes())
        return unsigned.model_copy(update={"signature": signature.hex()})


def verify_report(report: AssuranceReport, public_key: Ed25519PublicKey | bytes) -> bool:
    """Verify a report's signature against a public key. Returns True or raises.

    `public_key` may be an `Ed25519PublicKey` or PEM bytes. Two checks: the
    report's `kid` must match the key (so a report cannot point at a different
    key than the one verifying it), and the signature must verify over the
    report's canonical bytes.
    """
    key = _coerce_public_key(public_key)
    if report.kid != kid_for_public_key(key):
        raise ValueError("report kid does not match the public key it is verified against")
    try:
        key.verify(bytes.fromhex(report.signature), report.signing_bytes())
    except InvalidSignature as exc:
        raise ValueError("assurance report signature did not verify") from exc
    return True


def _coerce_public_key(public_key: Ed25519PublicKey | bytes) -> Ed25519PublicKey:
    if isinstance(public_key, Ed25519PublicKey):
        return public_key
    loaded = serialization.load_pem_public_key(public_key)
    if not isinstance(loaded, Ed25519PublicKey):
        raise ValueError("reporting public key must be Ed25519")
    return loaded


def collect_breaches(
    audit_log: AuditLog,
    *,
    protocol: str,
    window: ReportWindow,
    limit: int = 500,
) -> tuple[Breach, ...]:
    """Read breach rows for `protocol` within `window` from the audit log.

    Filters the append-only log by source == protocol and detected_at inside
    the window, oldest-first so the report reads chronologically.
    """
    rows = audit_log.query(kind="breach", limit=limit, newest_first=False)
    selected: list[Breach] = []
    for row in rows:
        breach = Breach.model_validate(row.payload)
        if breach.source != protocol:
            continue
        if window.start_ts <= breach.detected_at <= window.end_ts:
            selected.append(breach)
    return tuple(selected)


def build_report(
    signer: ReportSigner,
    *,
    protocol: str,
    window: ReportWindow,
    breaches: tuple[Breach, ...],
    recommendation: str,
    generated_at: float,
) -> AssuranceReport:
    """Pure build + sign of a report from an explicit breach set (no I/O)."""
    return signer.sign(
        protocol=protocol,
        window=window,
        breaches=breaches,
        recommendation=recommendation,
        generated_at=generated_at,
    )


def issue_report(
    audit_log: AuditLog,
    signer: ReportSigner,
    *,
    protocol: str,
    window: ReportWindow,
    recommendation: str,
    generated_at: float,
) -> AssuranceReport:
    """Build a report from the audit log, sign it, and record a `report` row.

    Single entry point for "an Assurance Report was issued": it reads the
    breaches it attests to from the same tamper-evident log it writes back to,
    so every issued report is itself audit-recoverable.
    """
    breaches = collect_breaches(audit_log, protocol=protocol, window=window)
    report = build_report(
        signer,
        protocol=protocol,
        window=window,
        breaches=breaches,
        recommendation=recommendation,
        generated_at=generated_at,
    )
    audit_log.record("report", report.model_dump(mode="json"), at=generated_at)
    return report


def generate_seed_hex() -> tuple[str, bytes]:
    """Return (seed_hex, public_pem) for a fresh reporting keypair.

    The seed hex goes in NAPG_REPORTING_SIGNING_KEY (secret, never committed);
    the public PEM is published so consumers can verify reports.
    """
    private_key = Ed25519PrivateKey.generate()
    seed = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return seed.hex(), public_pem


def default_reporting_public_key_path() -> Path:
    """`agent/config/reporting_public_key.pem`. Published/committed once set."""
    return Path(__file__).resolve().parents[1] / "config" / "reporting_public_key.pem"


__all__ = [
    "AssuranceReport",
    "ReportSigner",
    "ReportWindow",
    "build_report",
    "collect_breaches",
    "default_reporting_public_key_path",
    "generate_seed_hex",
    "issue_report",
    "kid_for_public_key",
    "verify_report",
]
