"""x402 payment surface for paid Assurance Reports.

Phase 4 Group B. Implements the x402 "exact" scheme over USDC so another agent
can pay for an Assurance Report: an unpaid request gets HTTP 402 with payment
requirements; a request carrying a valid signed payment gets the signed report.

The payment itself is an EIP-3009 `TransferWithAuthorization` over USDC, signed
by the payer (EIP-712). We verify the signature, the amount, the recipient, and
the expiry window; we do not move funds on-chain here -- in production the
verified authorization is forwarded to a facilitator that executes the transfer
(EIP-3009 lets anyone submit it). This module is the verify + account +
replay/idempotency layer; on-chain settlement is the facilitator wiring that
Phase 4 revenue reconciliation (4.14) checks against.

Replay and idempotency both ride on the append-only audit log -- the same
tamper-evident store the report itself is a view over:

- **Replay**: each payment `nonce` settles once. A second request reusing a
  settled nonce without a matching idempotency key is rejected.
- **Idempotency**: a retry that carries the same `Idempotency-Key` as the
  original settlement gets the original report back, never a second one.
"""

from __future__ import annotations

import base64
import binascii
import json
from decimal import Decimal, InvalidOperation

from eth_account import Account
from eth_account.messages import encode_typed_data
from pydantic import BaseModel, ConfigDict

from napg.audit import AuditLog
from napg.config import Network
from napg.policy.breaches import Breach
from napg.reporting import (
    AssuranceReport,
    ReportSigner,
    ReportWindow,
    build_report,
    collect_breaches,
)

X402_VERSION = 1
_USDC_DECIMALS = 6


class UsdcAsset(BaseModel):
    """The USDC contract for a network, with the EIP-712 domain fields its
    `transferWithAuthorization` signatures are verified under."""

    model_config = ConfigDict(frozen=True)

    address: str
    name: str
    version: str
    chain_id: int


# Public, stable USDC deployments + their EIP-712 domain name/version.
_USDC: dict[Network, UsdcAsset] = {
    "base-mainnet": UsdcAsset(
        address="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        name="USD Coin",
        version="2",
        chain_id=8453,
    ),
    "base-sepolia": UsdcAsset(
        address="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        name="USDC",
        version="2",
        chain_id=84532,
    ),
}


def usdc_for_network(network: Network) -> UsdcAsset:
    return _USDC[network]


def usdc_atomic(price_usdc: str) -> int:
    """Convert a decimal USDC string (e.g. "0.10") to 6-decimal atomic units."""
    try:
        return int((Decimal(price_usdc) * (10**_USDC_DECIMALS)).to_integral_value())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid USDC price: {price_usdc!r}") from exc


class X402Error(Exception):
    """A payment problem. `replay` marks a reused-nonce rejection (HTTP 409);
    everything else is a 402 (payment required / invalid)."""

    def __init__(self, reason: str, *, replay: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.replay = replay


class PaymentRequirements(BaseModel):
    """What the server demands for this resource (x402 'exact' scheme)."""

    model_config = ConfigDict(frozen=True)

    network: Network
    max_amount_required: int
    resource: str
    description: str
    pay_to: str
    asset: UsdcAsset
    max_timeout_seconds: int = 300

    def to_accepts(self) -> dict[str, object]:
        """The camelCase wire shape for the 402 body's `accepts` list."""
        return {
            "scheme": "exact",
            "network": self.network,
            "maxAmountRequired": str(self.max_amount_required),
            "resource": self.resource,
            "description": self.description,
            "mimeType": "application/json",
            "payTo": self.pay_to,
            "maxTimeoutSeconds": self.max_timeout_seconds,
            "asset": self.asset.address,
            "extra": {"name": self.asset.name, "version": self.asset.version},
        }


class Authorization(BaseModel):
    """The EIP-3009 TransferWithAuthorization fields the payer signed."""

    model_config = ConfigDict(frozen=True)

    from_address: str
    to: str
    value: int
    valid_after: int
    valid_before: int
    nonce: str  # 0x-prefixed bytes32 hex


class VerifiedPayment(BaseModel):
    model_config = ConfigDict(frozen=True)

    payer: str
    value: int
    nonce: str
    network: Network


def build_payment_requirements(
    *,
    network: Network,
    pay_to: str,
    price_atomic: int,
    resource: str,
    description: str,
) -> PaymentRequirements:
    return PaymentRequirements(
        network=network,
        max_amount_required=price_atomic,
        resource=resource,
        description=description,
        pay_to=pay_to,
        asset=usdc_for_network(network),
    )


def payment_required_body(
    requirements: PaymentRequirements, *, error: str = "payment required"
) -> dict[str, object]:
    return {
        "x402Version": X402_VERSION,
        "error": error,
        "accepts": [requirements.to_accepts()],
    }


def decode_payment_header(header: str) -> tuple[Authorization, str]:
    """Decode the base64 `X-PAYMENT` header into (authorization, signature).

    Raises X402Error on anything malformed so the caller can answer 402.
    """
    try:
        raw = base64.b64decode(header, validate=True)
        data = json.loads(raw)
    except (binascii.Error, ValueError) as exc:
        raise X402Error("malformed X-PAYMENT header") from exc
    if not isinstance(data, dict):
        raise X402Error("malformed X-PAYMENT payload")
    payload = data.get("payload")
    if not isinstance(payload, dict):
        raise X402Error("X-PAYMENT missing payload")
    signature = payload.get("signature")
    auth = payload.get("authorization")
    if not isinstance(signature, str) or not isinstance(auth, dict):
        raise X402Error("X-PAYMENT missing signature or authorization")
    try:
        authorization = Authorization(
            from_address=str(auth["from"]),
            to=str(auth["to"]),
            value=int(auth["value"]),
            valid_after=int(auth["validAfter"]),
            valid_before=int(auth["validBefore"]),
            nonce=str(auth["nonce"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise X402Error("X-PAYMENT authorization is incomplete") from exc
    return authorization, signature


def _typed_data(auth: Authorization, asset: UsdcAsset) -> dict[str, object]:
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": asset.name,
            "version": asset.version,
            "chainId": asset.chain_id,
            "verifyingContract": asset.address,
        },
        "message": {
            "from": auth.from_address,
            "to": auth.to,
            "value": auth.value,
            "validAfter": auth.valid_after,
            "validBefore": auth.valid_before,
            "nonce": bytes.fromhex(auth.nonce.removeprefix("0x")),
        },
    }


def verify_payment(
    authorization: Authorization,
    signature: str,
    requirements: PaymentRequirements,
    *,
    now: int,
) -> VerifiedPayment:
    """Verify a signed payment against the requirements. Raises X402Error.

    Checks (fail-closed, in order): recipient matches payTo, amount meets the
    price, the authorization window covers `now`, and the EIP-712 signature
    recovers to the declared payer.
    """
    if authorization.to.lower() != requirements.pay_to.lower():
        raise X402Error("payment recipient does not match payTo")
    if authorization.value < requirements.max_amount_required:
        raise X402Error("payment amount below the required price")
    if not (authorization.valid_after <= now < authorization.valid_before):
        raise X402Error("payment authorization expired or not yet valid")
    try:
        recovered = Account.recover_message(
            encode_typed_data(full_message=_typed_data(authorization, requirements.asset)),
            signature=signature,
        )
    except (ValueError, binascii.Error) as exc:
        raise X402Error("payment signature is malformed") from exc
    if recovered.lower() != authorization.from_address.lower():
        raise X402Error("payment signature does not recover to the payer")
    return VerifiedPayment(
        payer=authorization.from_address,
        value=authorization.value,
        nonce=authorization.nonce,
        network=requirements.network,
    )


def find_settled_payment(audit_log: AuditLog, nonce: str) -> dict[str, object] | None:
    """Return the stored payment payload for `nonce`, or None if unsettled."""
    for row in audit_log.query(kind="payment", limit=500, newest_first=True):
        if row.payload.get("nonce") == nonce:
            return row.payload
    return None


def summarize_recommendation(breaches: tuple[Breach, ...]) -> str:
    """Deterministic recommendation text from the breach set (no LLM call)."""
    if not breaches:
        return "healthy: no service-level breaches recorded in the window"
    return f"review: {len(breaches)} service-level breach(es) recorded in the window"


def settle_and_issue(
    audit_log: AuditLog,
    signer: ReportSigner,
    verified: VerifiedPayment,
    *,
    protocol: str,
    window: ReportWindow,
    generated_at: float,
    idempotency_key: str | None,
) -> tuple[AssuranceReport, bool]:
    """Settle one payment and issue its report. Returns (report, was_new).

    Replay/idempotency: a settled nonce only re-issues its original report when
    the retry carries the same idempotency key; any other reuse is a replay.
    The report's recommendation is derived from the breaches in the window.
    """
    existing = find_settled_payment(audit_log, verified.nonce)
    if existing is not None:
        stored_key = existing.get("idempotency_key")
        if idempotency_key is not None and stored_key == idempotency_key:
            return AssuranceReport.model_validate(existing["report"]), False
        raise X402Error("payment nonce already used", replay=True)

    breaches = collect_breaches(audit_log, protocol=protocol, window=window)
    report = build_report(
        signer,
        protocol=protocol,
        window=window,
        breaches=breaches,
        recommendation=summarize_recommendation(breaches),
        generated_at=generated_at,
    )
    audit_log.record("report", report.model_dump(mode="json"), at=generated_at)
    audit_log.record(
        "payment",
        {
            "nonce": verified.nonce,
            "payer": verified.payer,
            "value_atomic": verified.value,
            "asset": "USDC",
            "network": verified.network,
            "idempotency_key": idempotency_key,
            "report": report.model_dump(mode="json"),
        },
        at=generated_at,
    )
    return report, True


__all__ = [
    "X402_VERSION",
    "Authorization",
    "PaymentRequirements",
    "UsdcAsset",
    "VerifiedPayment",
    "X402Error",
    "build_payment_requirements",
    "decode_payment_header",
    "find_settled_payment",
    "payment_required_body",
    "settle_and_issue",
    "summarize_recommendation",
    "usdc_atomic",
    "usdc_for_network",
    "verify_payment",
]
