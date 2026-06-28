"""Tests for napg.payments — x402 payment requirements, EIP-712 verification, settlement."""

from __future__ import annotations

import base64
import json

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_account.signers.local import LocalAccount

from napg.audit import AuditLog
from napg.payments import (
    Authorization,
    PaymentRequirements,
    X402Error,
    _typed_data,
    build_payment_requirements,
    decode_payment_header,
    find_settled_payment,
    payment_required_body,
    settle_and_issue,
    summarize_recommendation,
    usdc_atomic,
    usdc_for_network,
    verify_payment,
)
from napg.policy.breaches import Breach
from napg.reporting import AssuranceReport, ReportSigner, ReportWindow, verify_report

_HMAC_KEY = "test-audit-hmac-key"
_PAY_TO = "0x000000000000000000000000000000000000d00d"
_NONCE_A = "0x" + "11" * 32
_NONCE_B = "0x" + "22" * 32


def _requirements(price_atomic: int = 100_000) -> PaymentRequirements:
    return build_payment_requirements(
        network="base-sepolia",
        pay_to=_PAY_TO,
        price_atomic=price_atomic,
        resource="/api/x402/assurance-report",
        description="test report",
    )


def make_payment_header(
    account: LocalAccount,
    requirements: PaymentRequirements,
    *,
    value: int,
    nonce: str,
    to: str | None = None,
    valid_after: int = 0,
    valid_before: int = 10**12,
) -> str:
    """Build a base64 X-PAYMENT header signed by `account` (EIP-712)."""
    auth = Authorization(
        from_address=account.address,
        to=to or requirements.pay_to,
        value=value,
        valid_after=valid_after,
        valid_before=valid_before,
        nonce=nonce,
    )
    typed = _typed_data(auth, requirements.asset)
    signed = account.sign_message(encode_typed_data(full_message=typed))
    sig = signed.signature.hex()
    if not sig.startswith("0x"):
        sig = "0x" + sig
    payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": requirements.network,
        "payload": {
            "signature": sig,
            "authorization": {
                "from": auth.from_address,
                "to": auth.to,
                "value": str(auth.value),
                "validAfter": auth.valid_after,
                "validBefore": auth.valid_before,
                "nonce": auth.nonce,
            },
        },
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def _breach(source: str = "aerodrome", detected_at: float = 100.0) -> Breach:
    return Breach(
        rule="peg_deviation_bps_max",
        source=source,
        severity="warn",
        threshold=50,
        actual=120,
        message="peg drift",
        detected_at=detected_at,
    )


# --- pure helpers -----------------------------------------------------------


def test_usdc_atomic_converts_decimal_string():
    assert usdc_atomic("0.10") == 100_000
    assert usdc_atomic("1") == 1_000_000
    assert usdc_atomic("0.000001") == 1


def test_usdc_atomic_rejects_garbage():
    with pytest.raises(ValueError, match="invalid USDC price"):
        usdc_atomic("not-a-number")


def test_usdc_for_network_has_domain_fields():
    asset = usdc_for_network("base-sepolia")
    assert asset.address.startswith("0x")
    assert asset.chain_id == 84532
    assert asset.version == "2"


def test_requirements_accepts_shape_is_camelcase():
    accepts = _requirements().to_accepts()
    assert accepts["scheme"] == "exact"
    assert accepts["maxAmountRequired"] == "100000"
    assert accepts["payTo"] == _PAY_TO
    assert accepts["extra"] == {"name": "USDC", "version": "2"}


def test_payment_required_body_wraps_requirements():
    body = payment_required_body(_requirements(), error="pay up")
    assert body["x402Version"] == 1
    assert body["error"] == "pay up"
    assert len(body["accepts"]) == 1


def test_summarize_recommendation():
    assert "no service-level breaches" in summarize_recommendation(())
    assert "1 service-level breach" in summarize_recommendation((_breach(),))


# --- header decoding --------------------------------------------------------


def test_decode_payment_header_round_trip():
    account = Account.create()
    requirements = _requirements()
    header = make_payment_header(account, requirements, value=100_000, nonce=_NONCE_A)
    auth, sig = decode_payment_header(header)
    assert auth.from_address == account.address
    assert auth.value == 100_000
    assert sig.startswith("0x")


def test_decode_payment_header_rejects_malformed_base64():
    with pytest.raises(X402Error, match="malformed X-PAYMENT"):
        decode_payment_header("!!!not base64!!!")


def test_decode_payment_header_rejects_missing_authorization():
    header = base64.b64encode(json.dumps({"payload": {"signature": "0x00"}}).encode()).decode()
    with pytest.raises(X402Error, match="missing signature or authorization"):
        decode_payment_header(header)


# --- verification -----------------------------------------------------------


def test_verify_payment_happy_path():
    account = Account.create()
    requirements = _requirements()
    header = make_payment_header(account, requirements, value=100_000, nonce=_NONCE_A)
    auth, sig = decode_payment_header(header)
    verified = verify_payment(auth, sig, requirements, now=500)
    assert verified.payer == account.address
    assert verified.value == 100_000
    assert verified.nonce == _NONCE_A


def test_verify_payment_rejects_wrong_recipient():
    account = Account.create()
    requirements = _requirements()
    other = "0x" + "ee" * 20
    header = make_payment_header(account, requirements, value=100_000, nonce=_NONCE_A, to=other)
    auth, sig = decode_payment_header(header)
    with pytest.raises(X402Error, match="recipient does not match"):
        verify_payment(auth, sig, requirements, now=500)


def test_verify_payment_rejects_low_amount():
    account = Account.create()
    requirements = _requirements()
    header = make_payment_header(account, requirements, value=99_999, nonce=_NONCE_A)
    auth, sig = decode_payment_header(header)
    with pytest.raises(X402Error, match="below the required price"):
        verify_payment(auth, sig, requirements, now=500)


def test_verify_payment_rejects_expired():
    account = Account.create()
    requirements = _requirements()
    header = make_payment_header(
        account, requirements, value=100_000, nonce=_NONCE_A, valid_before=1000
    )
    auth, sig = decode_payment_header(header)
    with pytest.raises(X402Error, match="expired or not yet valid"):
        verify_payment(auth, sig, requirements, now=2000)


def test_verify_payment_rejects_wrong_signer():
    account = Account.create()
    attacker = Account.create()
    requirements = _requirements()
    header = make_payment_header(account, requirements, value=100_000, nonce=_NONCE_A)
    auth, sig = decode_payment_header(header)
    # Claim the payment is from the attacker while it was signed by `account`.
    forged = auth.model_copy(update={"from_address": attacker.address})
    with pytest.raises(X402Error, match="does not recover to the payer"):
        verify_payment(forged, sig, requirements, now=500)


# --- settlement: report, replay, idempotency --------------------------------


def _verified(account: LocalAccount, requirements: PaymentRequirements, nonce: str):
    header = make_payment_header(account, requirements, value=100_000, nonce=nonce)
    auth, sig = decode_payment_header(header)
    return verify_payment(auth, sig, requirements, now=500)


def test_settle_writes_report_and_payment_rows_and_verifies(tmp_path):
    signer = ReportSigner.from_seed_hex("ab" * 32)
    requirements = _requirements()
    account = Account.create()
    with AuditLog(tmp_path / "audit.db", _HMAC_KEY) as log:
        log.record_breaches((_breach("aerodrome", 100.0),))
        verified = _verified(account, requirements, _NONCE_A)
        report, was_new = settle_and_issue(
            log,
            signer,
            verified,
            protocol="aerodrome",
            window=ReportWindow(start_ts=0.0, end_ts=1000.0),
            generated_at=500.0,
            idempotency_key="key-1",
        )
        report_rows = log.query(kind="report", limit=10)
        payment_rows = log.query(kind="payment", limit=10)

    assert was_new is True
    assert len(report.breaches) == 1
    assert "1 service-level breach" in report.recommendation
    assert verify_report(report, signer.public_pem()) is True
    assert len(report_rows) == 1
    assert len(payment_rows) == 1
    assert payment_rows[0].payload["payer"] == account.address
    assert payment_rows[0].payload["nonce"] == _NONCE_A


def test_replay_without_matching_idempotency_key_is_rejected(tmp_path):
    signer = ReportSigner.from_seed_hex("ab" * 32)
    requirements = _requirements()
    account = Account.create()
    with AuditLog(tmp_path / "audit.db", _HMAC_KEY) as log:
        verified = _verified(account, requirements, _NONCE_A)
        settle_and_issue(
            log,
            signer,
            verified,
            protocol="aerodrome",
            window=ReportWindow(start_ts=0.0, end_ts=1000.0),
            generated_at=500.0,
            idempotency_key="key-1",
        )
        with pytest.raises(X402Error) as exc:
            settle_and_issue(
                log,
                signer,
                verified,
                protocol="aerodrome",
                window=ReportWindow(start_ts=0.0, end_ts=1000.0),
                generated_at=600.0,
                idempotency_key=None,
            )
        # only one report despite two settle attempts
        assert len(log.query(kind="report", limit=10)) == 1
    assert exc.value.replay is True


def test_idempotent_retry_returns_the_original_report(tmp_path):
    signer = ReportSigner.from_seed_hex("ab" * 32)
    requirements = _requirements()
    account = Account.create()
    with AuditLog(tmp_path / "audit.db", _HMAC_KEY) as log:
        verified = _verified(account, requirements, _NONCE_A)
        first, first_new = settle_and_issue(
            log,
            signer,
            verified,
            protocol="aerodrome",
            window=ReportWindow(start_ts=0.0, end_ts=1000.0),
            generated_at=500.0,
            idempotency_key="key-1",
        )
        second, second_new = settle_and_issue(
            log,
            signer,
            verified,
            protocol="aerodrome",
            window=ReportWindow(start_ts=0.0, end_ts=1000.0),
            generated_at=999.0,
            idempotency_key="key-1",
        )
        assert len(log.query(kind="report", limit=10)) == 1

    assert first_new is True
    assert second_new is False
    # Byte-identical (same signature, same generated_at) -- not a fresh report.
    assert second.model_dump() == first.model_dump()


def test_find_settled_payment(tmp_path):
    signer = ReportSigner.from_seed_hex("ab" * 32)
    requirements = _requirements()
    account = Account.create()
    with AuditLog(tmp_path / "audit.db", _HMAC_KEY) as log:
        assert find_settled_payment(log, _NONCE_A) is None
        verified = _verified(account, requirements, _NONCE_A)
        settle_and_issue(
            log,
            signer,
            verified,
            protocol="aerodrome",
            window=ReportWindow(start_ts=0.0, end_ts=1000.0),
            generated_at=500.0,
            idempotency_key=None,
        )
        found = find_settled_payment(log, _NONCE_A)
        assert found is not None
        assert found["nonce"] == _NONCE_A
        assert isinstance(AssuranceReport.model_validate(found["report"]), AssuranceReport)
