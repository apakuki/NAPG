"""Tests for napg.api — the FastAPI read endpoint for the dashboard."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from napg.api import create_app
from napg.config import Settings
from napg.monitor.aerodrome import LiquidityProbe
from napg.monitor.morpho import MarketState, MorphoPoll
from napg.monitor.rpc import BlockSnapshot, HeartbeatResult

HASH_A = "0x" + "aa" * 32
HASH_B = "0x" + "bb" * 32


def _settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[call-arg]


def _heartbeat() -> HeartbeatResult:
    return HeartbeatResult(
        rpc_url="https://sepolia.example/<redacted>",
        chain_id=84532,
        latency_ms=123.4,
        block=BlockSnapshot(number=42, hash=HASH_A, parent_hash=HASH_B, timestamp=1_700_000_000),
        reorg_detected=False,
        observed_at=1_700_000_001.0,
    )


def _liquidity() -> LiquidityProbe:
    return LiquidityProbe(
        chain_id=8453,
        sell_token="0xUSDC",
        buy_token="0xUSDT",
        sell_amount=10_000_000_000,
        buy_amount=10_001_000_000,
        liquidity_available=True,
        quoted_rate=1.0001,
        peg_deviation_bps=1,
        sources=("Aerodrome_V3",),
        block_number=1234,
        latency_ms=200.0,
        observed_at=1_700_000_002.0,
    )


def _morpho() -> MorphoPoll:
    return MorphoPoll(
        chain_id=8453,
        block_number=1234,
        block_timestamp=1_700_000_000,
        markets=(
            MarketState(
                label="WETH-USDC",
                market_id="0x" + "11" * 32,
                loan_symbol="USDC",
                collateral_symbol="WETH",
                total_supply_assets=10**13,
                total_borrow_assets=8 * 10**12,
                utilization_bps=8000,
                last_update=1_700_000_000,
                staleness_seconds=10,
                block_number=1234,
                observed_at=1_700_000_002.0,
            ),
        ),
        latency_ms=80.0,
        observed_at=1_700_000_002.0,
    )


def test_health_returns_ok():
    client = TestClient(create_app(settings=_settings()))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_returns_three_healthy_cards():
    settings = _settings(
        NAPG_NETWORK="base-sepolia",
        BASE_SEPOLIA_RPC_URL="https://sepolia.example/rpc",
        BASE_RPC_URL="https://mainnet.example/rpc",
        ZEROX_API_KEY="test-key",
    )
    with (
        patch("napg.api._heartbeat", return_value=_heartbeat()),
        patch("napg.api._aerodrome", return_value=_liquidity()),
        patch("napg.api._morpho", return_value=_morpho()),
    ):
        client = TestClient(create_app(settings=settings))
        response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["heartbeat"]["chain_id"] == 84532
    assert body["heartbeat"]["block"]["number"] == 42
    assert body["aerodrome"]["sources"] == ["Aerodrome_V3"]
    assert body["morpho"]["markets"][0]["label"] == "WETH-USDC"


def test_status_isolates_per_card_failures():
    """One broken probe must not break the other two."""
    settings = _settings(BASE_SEPOLIA_RPC_URL="https://sepolia.example/rpc")
    with (
        patch("napg.api._heartbeat", return_value=_heartbeat()),
        patch(
            "napg.api._aerodrome",
            return_value=__import__("napg.api", fromlist=["CardError"]).CardError(
                error="ZEROX_API_KEY not set"
            ),
        ),
        patch("napg.api._morpho", return_value=_morpho()),
    ):
        client = TestClient(create_app(settings=settings))
        response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["heartbeat"]["chain_id"] == 84532
    assert body["aerodrome"] == {"error": "ZEROX_API_KEY not set"}
    assert body["morpho"]["markets"][0]["label"] == "WETH-USDC"


def test_heartbeat_card_reports_missing_rpc_url():
    """No primary RPC configured → card-level error, not a 500."""
    from napg.api import _heartbeat as probe

    settings = _settings(NAPG_NETWORK="base-sepolia")  # no URL set
    result = probe(settings)
    assert hasattr(result, "error")
    assert "BASE_SEPOLIA_RPC_URL" in result.error  # type: ignore[union-attr]


def test_aerodrome_card_reports_missing_api_key():
    from napg.api import _aerodrome as probe

    settings = _settings()
    result = probe(settings)
    assert hasattr(result, "error")
    assert "ZEROX_API_KEY" in result.error  # type: ignore[union-attr]


def test_morpho_card_reports_missing_mainnet_rpc():
    from napg.api import _morpho as probe

    settings = _settings()
    result = probe(settings)
    assert hasattr(result, "error")
    assert "BASE_RPC_URL" in result.error  # type: ignore[union-attr]


def test_heartbeat_card_wraps_probe_exception_as_carderror():
    from napg.api import _heartbeat as probe

    settings = _settings(BASE_SEPOLIA_RPC_URL="https://sepolia.example/rpc")

    class _Boom(Exception):
        pass

    def _explode(*_a, **_kw):
        raise _Boom("provider unreachable")

    with patch("napg.api.RpcHeartbeat", side_effect=_explode):
        result = probe(settings)

    assert hasattr(result, "error")
    assert "_Boom" in result.error  # type: ignore[union-attr]


def test_aerodrome_card_wraps_probe_exception_as_carderror():
    from napg.api import _aerodrome as probe

    settings = _settings(ZEROX_API_KEY="test-key")

    class _Boom(Exception):
        pass

    def _explode(*_a, **_kw):
        raise _Boom("0x rate limit")

    with patch("napg.api.AerodromeMonitor", side_effect=_explode):
        result = probe(settings)

    assert hasattr(result, "error")
    assert "_Boom" in result.error  # type: ignore[union-attr]


def test_morpho_card_wraps_probe_exception_as_carderror():
    from napg.api import _morpho as probe

    settings = _settings(BASE_RPC_URL="https://mainnet.example/rpc")

    class _Boom(Exception):
        pass

    def _explode(*_a, **_kw):
        raise _Boom("contract revert")

    with patch("napg.api.MorphoMonitor", side_effect=_explode):
        result = probe(settings)

    assert hasattr(result, "error")
    assert "_Boom" in result.error  # type: ignore[union-attr]


def _seed_breaches(audit_db: str, hmac_key: str) -> None:
    """Populate the audit DB with three breach rows across two sources."""
    from napg.audit import AuditLog
    from napg.policy.breaches import Breach

    with AuditLog(audit_db, hmac_key) as log:
        log.record_breaches(
            [
                Breach(
                    rule="rpc_latency_ms_max",
                    source="heartbeat",
                    severity="warn",
                    threshold=2000,
                    actual=4500,
                    message="RPC heartbeat latency 4500ms > 2000ms",
                    detected_at=1_700_000_000.0,
                ),
                Breach(
                    rule="peg_deviation_bps_max",
                    source="aerodrome",
                    severity="warn",
                    threshold=50,
                    actual=120,
                    message="USDC/USDT peg drifted 120bps",
                    detected_at=1_700_000_010.0,
                ),
            ],
            at=1_700_000_010.0,
        )
        log.record_breaches(
            [
                Breach(
                    rule="market_utilization_bps_max",
                    source="morpho",
                    severity="warn",
                    threshold=9500,
                    actual=9700,
                    message="Morpho WETH-USDC utilisation 97%",
                    detected_at=1_700_000_020.0,
                ),
            ],
            at=1_700_000_020.0,
        )


def test_breaches_endpoint_503s_when_hmac_key_unset(tmp_path):
    settings = _settings(NAPG_AUDIT_DB=str(tmp_path / "audit.db"))
    client = TestClient(create_app(settings=settings))
    response = client.get("/api/audit/breaches")
    assert response.status_code == 503
    assert "NAPG_AUDIT_HMAC_KEY" in response.json()["detail"]


def test_breaches_endpoint_returns_recent_rows_newest_first(tmp_path):
    db = tmp_path / "audit.db"
    settings = _settings(
        NAPG_AUDIT_DB=str(db),
        NAPG_AUDIT_HMAC_KEY="test-key-do-not-use-in-prod",
    )
    _seed_breaches(str(db), "test-key-do-not-use-in-prod")
    client = TestClient(create_app(settings=settings))
    response = client.get("/api/audit/breaches")
    assert response.status_code == 200
    body = response.json()
    assert body["total_returned"] == 3
    # Newest first: morpho row was the most recent insert.
    assert body["items"][0]["payload"]["source"] == "morpho"
    assert body["items"][-1]["payload"]["source"] == "heartbeat"
    # No HMAC leakage onto the wire.
    assert "hmac" not in body["items"][0]


def test_breaches_endpoint_filters_by_source(tmp_path):
    db = tmp_path / "audit.db"
    settings = _settings(
        NAPG_AUDIT_DB=str(db),
        NAPG_AUDIT_HMAC_KEY="test-key",
    )
    _seed_breaches(str(db), "test-key")
    client = TestClient(create_app(settings=settings))
    response = client.get("/api/audit/breaches?source=aerodrome")
    assert response.status_code == 200
    body = response.json()
    assert body["total_returned"] == 1
    assert body["items"][0]["payload"]["source"] == "aerodrome"
    assert body["items"][0]["payload"]["rule"] == "peg_deviation_bps_max"


def test_breaches_endpoint_clamps_limit(tmp_path):
    db = tmp_path / "audit.db"
    settings = _settings(
        NAPG_AUDIT_DB=str(db),
        NAPG_AUDIT_HMAC_KEY="test-key",
    )
    _seed_breaches(str(db), "test-key")
    client = TestClient(create_app(settings=settings))
    # FastAPI Query rejects out-of-range limits at the validator layer.
    response = client.get("/api/audit/breaches?limit=999")
    assert response.status_code == 422
    response = client.get("/api/audit/breaches?limit=0")
    assert response.status_code == 422


# --- x402 paid Assurance Report endpoint ------------------------------------

from eth_account import Account  # noqa: E402

from napg.x402 import build_payment_requirements, usdc_atomic  # noqa: E402
from tests.test_x402 import make_payment_header  # noqa: E402

_REPORTING_SEED = "cd" * 32
_X402_PAY_TO = "0x000000000000000000000000000000000000d00d"
_X402_NONCE = "0x" + "33" * 32


def _x402_settings(tmp_path, **extra):
    return _settings(
        NAPG_NETWORK="base-sepolia",
        NAPG_AUDIT_DB=str(tmp_path / "audit.db"),
        NAPG_AUDIT_HMAC_KEY="test-key",
        NAPG_REPORTING_SIGNING_KEY=_REPORTING_SEED,
        NAPG_X402_PAY_TO=_X402_PAY_TO,
        **extra,
    )


def _signed_header(account, *, nonce=_X402_NONCE, value=100_000):
    requirements = build_payment_requirements(
        network="base-sepolia",
        pay_to=_X402_PAY_TO,
        price_atomic=usdc_atomic("0.10"),
        resource="/api/x402/assurance-report",
        description="test",
    )
    return make_payment_header(account, requirements, value=value, nonce=nonce)


def test_x402_returns_402_without_payment(tmp_path):
    client = TestClient(create_app(settings=_x402_settings(tmp_path)))
    response = client.post("/api/x402/assurance-report", json={"protocol": "aerodrome"})
    assert response.status_code == 402
    body = response.json()
    assert body["x402Version"] == 1
    assert body["accepts"][0]["payTo"] == _X402_PAY_TO


def test_x402_503_when_reporting_key_unset(tmp_path):
    settings = _settings(
        NAPG_AUDIT_DB=str(tmp_path / "audit.db"),
        NAPG_AUDIT_HMAC_KEY="test-key",
        NAPG_X402_PAY_TO=_X402_PAY_TO,
    )
    client = TestClient(create_app(settings=settings))
    response = client.post("/api/x402/assurance-report", json={"protocol": "aerodrome"})
    assert response.status_code == 503
    assert "reporting key" in response.json()["detail"]


def test_x402_503_when_pay_to_unset(tmp_path):
    settings = _settings(
        NAPG_AUDIT_DB=str(tmp_path / "audit.db"),
        NAPG_AUDIT_HMAC_KEY="test-key",
        NAPG_REPORTING_SIGNING_KEY=_REPORTING_SEED,
    )
    client = TestClient(create_app(settings=settings))
    response = client.post("/api/x402/assurance-report", json={"protocol": "aerodrome"})
    assert response.status_code == 503
    assert "payTo" in response.json()["detail"]


def test_x402_paid_returns_signed_report(tmp_path):
    client = TestClient(create_app(settings=_x402_settings(tmp_path)))
    account = Account.create()
    response = client.post(
        "/api/x402/assurance-report",
        json={"protocol": "aerodrome"},
        headers={"X-PAYMENT": _signed_header(account)},
    )
    assert response.status_code == 200
    report = response.json()
    assert report["protocol"] == "aerodrome"
    assert report["signature"]
    assert report["kid"]


def test_x402_rejects_underpayment_with_402(tmp_path):
    client = TestClient(create_app(settings=_x402_settings(tmp_path)))
    account = Account.create()
    response = client.post(
        "/api/x402/assurance-report",
        json={"protocol": "aerodrome"},
        headers={"X-PAYMENT": _signed_header(account, value=1)},
    )
    assert response.status_code == 402
    assert "below the required price" in response.json()["error"]


def test_x402_replayed_nonce_is_rejected_409(tmp_path):
    client = TestClient(create_app(settings=_x402_settings(tmp_path)))
    account = Account.create()
    header = _signed_header(account)
    first = client.post(
        "/api/x402/assurance-report",
        json={"protocol": "aerodrome"},
        headers={"X-PAYMENT": header},
    )
    assert first.status_code == 200
    # Same nonce, no idempotency key -> replay.
    second = client.post(
        "/api/x402/assurance-report",
        json={"protocol": "aerodrome"},
        headers={"X-PAYMENT": header},
    )
    assert second.status_code == 409
    assert "already used" in second.json()["error"]


def test_x402_idempotent_retry_returns_original_report(tmp_path):
    client = TestClient(create_app(settings=_x402_settings(tmp_path)))
    account = Account.create()
    header = _signed_header(account)
    headers = {"X-PAYMENT": header, "Idempotency-Key": "retry-1"}
    first = client.post(
        "/api/x402/assurance-report", json={"protocol": "aerodrome"}, headers=headers
    )
    second = client.post(
        "/api/x402/assurance-report", json={"protocol": "aerodrome"}, headers=headers
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()


# --- Guardian Mode entitlement endpoint -------------------------------------

from napg.audit import AuditLog  # noqa: E402
from napg.guardian import grant_entitlement  # noqa: E402


def test_guardian_status_503_when_hmac_unset(tmp_path):
    settings = _settings(NAPG_AUDIT_DB=str(tmp_path / "audit.db"))
    client = TestClient(create_app(settings=settings))
    assert client.get("/api/guardian/status?fid=123").status_code == 503


def test_guardian_status_not_entitled_without_record(tmp_path):
    settings = _settings(NAPG_AUDIT_DB=str(tmp_path / "audit.db"), NAPG_AUDIT_HMAC_KEY="test-key")
    client = TestClient(create_app(settings=settings))
    body = client.get("/api/guardian/status?fid=123").json()
    assert body == {"fid": 123, "entitled": False, "plan": None, "expires_at": None}


def test_guardian_status_ignores_forged_client_claim(tmp_path):
    settings = _settings(NAPG_AUDIT_DB=str(tmp_path / "audit.db"), NAPG_AUDIT_HMAC_KEY="test-key")
    client = TestClient(create_app(settings=settings))
    # A forged entitlement claim in headers must not grant access.
    response = client.get(
        "/api/guardian/status?fid=123",
        headers={"x-entitled": "true", "x-guardian-plan": "guardian-monthly"},
    )
    assert response.json()["entitled"] is False


def test_guardian_status_entitled_after_grant(tmp_path):
    db = tmp_path / "audit.db"
    settings = _settings(NAPG_AUDIT_DB=str(db), NAPG_AUDIT_HMAC_KEY="test-key")
    import time as _time

    with AuditLog(str(db), "test-key") as log:
        grant_entitlement(log, fid=123, granted_at=_time.time(), duration_seconds=30 * 86_400)
    client = TestClient(create_app(settings=settings))
    body = client.get("/api/guardian/status?fid=123").json()
    assert body["entitled"] is True
    assert body["plan"] == "guardian-monthly"
