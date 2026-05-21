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
