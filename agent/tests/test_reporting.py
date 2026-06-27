"""Tests for napg.reporting — Assurance Report schema, signing, verification."""

from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from napg.audit import AuditLog
from napg.policy.breaches import Breach
from napg.reporting import (
    AssuranceReport,
    ReportSigner,
    ReportWindow,
    build_report,
    collect_breaches,
    generate_seed_hex,
    issue_report,
    kid_for_public_key,
    verify_report,
)

_HMAC_KEY = "test-audit-hmac-key"


def _signer() -> ReportSigner:
    return ReportSigner(Ed25519PrivateKey.generate())


def _breach(source: str, detected_at: float, rule: str = "rpc_latency_ms_max") -> Breach:
    return Breach(
        rule=rule,
        source=source,
        severity="warn",
        threshold=2000,
        actual=4500,
        message="latency over threshold",
        detected_at=detected_at,
    )


def _window(start: float = 0.0, end: float = 1_000_000.0) -> ReportWindow:
    return ReportWindow(start_ts=start, end_ts=end)


def test_kid_differs_across_keys_and_matches_its_own_public_key():
    signer_a = _signer()
    signer_b = _signer()
    assert signer_a.kid != signer_b.kid
    # The kid is a pure function of the public key: deriving it directly from a
    # seed's public key matches the signer built from that same seed.
    seed_hex, _ = generate_seed_hex()
    public_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex)).public_key()
    assert ReportSigner.from_seed_hex(seed_hex).kid == kid_for_public_key(public_key)


def test_sign_then_verify_round_trip():
    signer = _signer()
    report = build_report(
        signer,
        protocol="aerodrome",
        window=_window(),
        breaches=(_breach("aerodrome", 100.0),),
        recommendation="hold",
        generated_at=500.0,
    )
    assert report.kid == signer.kid
    assert report.signature
    assert verify_report(report, signer.public_pem()) is True


def test_verify_rejects_tampered_recommendation():
    signer = _signer()
    report = build_report(
        signer,
        protocol="aerodrome",
        window=_window(),
        breaches=(),
        recommendation="hold",
        generated_at=500.0,
    )
    tampered = report.model_copy(update={"recommendation": "migrate_to_safe"})
    with pytest.raises(ValueError, match="did not verify"):
        verify_report(tampered, signer.public_pem())


def test_verify_rejects_tampered_breaches():
    signer = _signer()
    report = build_report(
        signer,
        protocol="aerodrome",
        window=_window(),
        breaches=(_breach("aerodrome", 100.0),),
        recommendation="hold",
        generated_at=500.0,
    )
    tampered = report.model_copy(update={"breaches": ()})
    with pytest.raises(ValueError, match="did not verify"):
        verify_report(tampered, signer.public_pem())


def test_verify_accepts_a_public_key_object():
    seed_hex, _ = generate_seed_hex()
    signer = ReportSigner.from_seed_hex(seed_hex)
    report = build_report(
        signer,
        protocol="aerodrome",
        window=_window(),
        breaches=(),
        recommendation="hold",
        generated_at=1.0,
    )
    public_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex)).public_key()
    # Pass the Ed25519PublicKey object directly (not PEM bytes).
    assert verify_report(report, public_key) is True


def test_verify_rejects_a_non_ed25519_public_key():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    signer = _signer()
    report = build_report(
        signer,
        protocol="aerodrome",
        window=_window(),
        breaches=(),
        recommendation="hold",
        generated_at=1.0,
    )
    rsa_pem = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    with pytest.raises(ValueError, match="must be Ed25519"):
        verify_report(report, rsa_pem)


def test_default_reporting_public_key_path_points_at_config():
    from napg.reporting import default_reporting_public_key_path

    path = default_reporting_public_key_path()
    assert path.name == "reporting_public_key.pem"
    assert path.parent.name == "config"


def test_verify_rejects_wrong_key():
    signer = _signer()
    other = _signer()
    report = build_report(
        signer,
        protocol="aerodrome",
        window=_window(),
        breaches=(),
        recommendation="hold",
        generated_at=500.0,
    )
    with pytest.raises(ValueError, match="kid does not match"):
        verify_report(report, other.public_pem())


def test_from_seed_hex_round_trips_kid_and_signature():
    seed_hex, _public_pem = generate_seed_hex()
    signer_one = ReportSigner.from_seed_hex(seed_hex)
    signer_two = ReportSigner.from_seed_hex(seed_hex)
    assert signer_one.kid == signer_two.kid
    report = build_report(
        signer_one,
        protocol="morpho",
        window=_window(),
        breaches=(),
        recommendation="hold",
        generated_at=1.0,
    )
    assert verify_report(report, signer_two.public_pem()) is True


def test_from_seed_hex_rejects_wrong_length():
    with pytest.raises(ValueError, match="32-byte hex seed"):
        ReportSigner.from_seed_hex("00ff")


def test_from_settings_requires_a_key():
    class _NoKey:
        reporting_signing_key = None

    with pytest.raises(RuntimeError, match="No reporting key configured"):
        ReportSigner.from_settings(_NoKey())


def test_from_settings_builds_signer_from_seed():
    seed_hex, _ = generate_seed_hex()

    class _WithKey:
        reporting_signing_key = seed_hex

    signer = ReportSigner.from_settings(_WithKey())
    assert signer.kid == ReportSigner.from_seed_hex(seed_hex).kid


def test_reporting_key_is_not_the_wallet_key():
    """Ed25519 reporting key is a different curve from the secp256k1 wallet, so a
    report signature can never double as an on-chain tx signature."""
    signer = _signer()
    report = build_report(
        signer,
        protocol="aerodrome",
        window=_window(),
        breaches=(),
        recommendation="hold",
        generated_at=1.0,
    )
    # Ed25519 signatures are 64 bytes; an EVM ECDSA signature is 65. The shapes
    # differ, which is the structural guarantee we want.
    assert len(bytes.fromhex(report.signature)) == 64


def test_collect_breaches_filters_by_source_and_window(tmp_path):
    db = tmp_path / "audit.db"
    with AuditLog(db, _HMAC_KEY) as log:
        log.record_breaches(
            (
                _breach("aerodrome", 100.0),
                _breach("heartbeat", 150.0),
                _breach("aerodrome", 9_999_999.0),  # outside the window
            )
        )
        window = _window(0.0, 1_000.0)
        breaches = collect_breaches(log, protocol="aerodrome", window=window)
    assert len(breaches) == 1
    assert breaches[0].source == "aerodrome"
    assert breaches[0].detected_at == 100.0


def test_issue_report_writes_a_report_row_and_verifies(tmp_path):
    db = tmp_path / "audit.db"
    signer = _signer()
    with AuditLog(db, _HMAC_KEY) as log:
        log.record_breaches((_breach("aerodrome", 100.0),))
        report = issue_report(
            log,
            signer,
            protocol="aerodrome",
            window=_window(0.0, 1_000.0),
            recommendation="hold",
            generated_at=500.0,
        )
        rows = log.query(kind="report", limit=10)
    assert len(rows) == 1
    assert rows[0].payload["kid"] == signer.kid
    # The recorded row round-trips back to a verifiable report.
    recorded = AssuranceReport.model_validate(rows[0].payload)
    assert verify_report(recorded, signer.public_pem()) is True
    assert len(report.breaches) == 1


def test_issued_report_payload_never_contains_the_private_seed(tmp_path):
    db = tmp_path / "audit.db"
    seed_hex, _ = generate_seed_hex()
    signer = ReportSigner.from_seed_hex(seed_hex)
    with AuditLog(db, _HMAC_KEY) as log:
        issue_report(
            log,
            signer,
            protocol="aerodrome",
            window=_window(),
            recommendation="hold",
            generated_at=1.0,
        )
        rows = log.query(kind="report", limit=10)
    serialized = json.dumps(rows[0].payload)
    assert seed_hex not in serialized
