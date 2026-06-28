"""FastAPI read endpoint that powers the Service Assurance Dashboard.

One endpoint, `GET /api/status`, returns live monitor data for the three
Phase 1 cards: RPC heartbeat, Aerodrome USDC/USDT, Morpho Blue. Each card
is reported independently — if one probe fails or its env isn't set, that
card carries an `error` field while the others still return data. The
endpoint never partial-500s, so the dashboard can render every healthy
card on every poll.

The probes are blocking (web3 / httpx sync), so they run in a thread pool
via `asyncio.to_thread` and fan out in parallel per request. A 10s poll
from the UI translates to one parallel burst of probes per cycle.

This module deliberately does not add CORS middleware: the production
shape is the Next.js route handler proxying server-side, so the browser
never talks to this API directly. Binding to 127.0.0.1 in dev keeps the
attack surface honest.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from napg.audit import AuditLog
from napg.config import Settings
from napg.guardian import GuardianStatus, entitlement_status
from napg.monitor.aerodrome import AerodromeMonitor, LiquidityProbe
from napg.monitor.morpho import MorphoMonitor, MorphoPoll
from napg.monitor.resilience import CircuitBreaker, FailoverRpcHeartbeat, RateLimiter
from napg.monitor.rpc import HeartbeatResult, RpcHeartbeat
from napg.payments import (
    X402Error,
    build_payment_requirements,
    decode_payment_header,
    payment_required_body,
    settle_and_issue,
    usdc_atomic,
    verify_payment,
)
from napg.reporting import ReportSigner, ReportWindow

# Per-upstream gates. Aerodrome and Morpho share the same Phase 1 defaults as
# `FailoverRpcHeartbeat`: 5 req/s sustained / burst of 5, breaker opens after 3
# consecutive failures and cools down 30 s. Each upstream gets its own
# limiter+breaker so a flaky 0x doesn't trip the Morpho circuit.
_AERODROME_LIMITER = RateLimiter(rate_per_sec=5.0, capacity=5)
_AERODROME_BREAKER = CircuitBreaker(failure_threshold=3, cooldown_s=30.0)
_MORPHO_LIMITER = RateLimiter(rate_per_sec=5.0, capacity=5)
_MORPHO_BREAKER = CircuitBreaker(failure_threshold=3, cooldown_s=30.0)

logger = logging.getLogger("napg.api")


class CardError(BaseModel):
    """Per-card failure envelope. `error` is a short, redacted-friendly summary."""

    model_config = ConfigDict(frozen=True)

    error: str


class StatusResponse(BaseModel):
    """One snapshot of monitor state. Each card is either probe output or CardError."""

    model_config = ConfigDict(frozen=True)

    heartbeat: HeartbeatResult | CardError
    aerodrome: LiquidityProbe | CardError
    morpho: MorphoPoll | CardError


class BreachFeedItem(BaseModel):
    """One breach row reshaped for the UI feed. Drops the HMAC (not display).

    `payload` is the parsed breach: rule, source, severity, threshold, actual,
    message, detected_at. The UI uses `source` to filter the per-protocol
    detail page, and the rest to render the row.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    recorded_at: str
    payload: dict[str, Any]


class BreachFeedResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[BreachFeedItem]
    total_returned: int


class X402ReportRequest(BaseModel):
    """Body for the paid Assurance Report endpoint."""

    model_config = ConfigDict(frozen=True)

    protocol: str = Field(min_length=1, max_length=64)
    window_seconds: int = Field(default=86_400, ge=1, le=2_592_000)


def _heartbeat(settings: Settings) -> HeartbeatResult | CardError:
    try:
        urls = settings.active_rpc_urls()
    except RuntimeError as exc:
        return CardError(error=str(exc))
    try:
        hearts = [RpcHeartbeat(u) for u in urls]
        pool = FailoverRpcHeartbeat(hearts)
        return pool.tick()
    except Exception as exc:
        logger.warning("heartbeat probe failed: %s", type(exc).__name__)
        return CardError(error=f"{type(exc).__name__}: {exc}")


def _aerodrome(settings: Settings) -> LiquidityProbe | CardError:
    if not settings.zerox_api_key:
        return CardError(error="ZEROX_API_KEY not set")
    try:
        return AerodromeMonitor(
            api_key=settings.zerox_api_key,
            limiter=_AERODROME_LIMITER,
            breaker=_AERODROME_BREAKER,
        ).tick()
    except Exception as exc:
        logger.warning("aerodrome probe failed: %s", type(exc).__name__)
        return CardError(error=f"{type(exc).__name__}: {exc}")


def _morpho(settings: Settings) -> MorphoPoll | CardError:
    if not settings.base_rpc_url:
        return CardError(error="BASE_RPC_URL not set (Morpho needs Base mainnet)")
    try:
        return MorphoMonitor(
            settings.base_rpc_url,
            limiter=_MORPHO_LIMITER,
            breaker=_MORPHO_BREAKER,
        ).tick()
    except Exception as exc:
        logger.warning("morpho probe failed: %s", type(exc).__name__)
        return CardError(error=f"{type(exc).__name__}: {exc}")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. `settings` injectable so tests can stub env."""
    resolved = settings if settings is not None else Settings()
    app = FastAPI(title="NAPG Service Assurance API", version="0.1.0")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/status", response_model=StatusResponse)
    async def status() -> StatusResponse:
        heartbeat, aerodrome, morpho = await asyncio.gather(
            asyncio.to_thread(_heartbeat, resolved),
            asyncio.to_thread(_aerodrome, resolved),
            asyncio.to_thread(_morpho, resolved),
        )
        return StatusResponse(
            heartbeat=heartbeat,
            aerodrome=aerodrome,
            morpho=morpho,
        )

    @app.get("/api/audit/breaches", response_model=BreachFeedResponse)
    async def breaches(
        limit: int = Query(default=50, ge=1, le=200),
        source: str | None = Query(default=None, max_length=64),
    ) -> BreachFeedResponse:
        """Most recent breach rows from the append-only audit log.

        `source` filters to a single probe (`heartbeat`, `aerodrome`, `morpho`)
        client-side once the rows are read; the audit log is keyed by kind, not
        source, so we pull `limit + slack` rows and filter in Python. Small
        enough at Phase 3 volumes that pagination keys can wait for Phase 5.
        """
        if not resolved.audit_hmac_key:
            raise HTTPException(
                status_code=503,
                detail="audit log not configured (NAPG_AUDIT_HMAC_KEY unset)",
            )

        def read_breaches() -> list[BreachFeedItem]:
            with AuditLog(resolved.audit_db_path, resolved.audit_hmac_key) as log:
                rows = log.query(kind="breach", limit=limit)
            items = [
                BreachFeedItem(id=row.id, recorded_at=row.recorded_at, payload=row.payload)
                for row in rows
            ]
            if source is not None:
                items = [it for it in items if it.payload.get("source") == source]
            return items

        items = await asyncio.to_thread(read_breaches)
        return BreachFeedResponse(items=items, total_returned=len(items))

    @app.post("/api/x402/assurance-report")
    async def x402_assurance_report(
        body: X402ReportRequest,
        x_payment: str | None = Header(default=None, alias="X-PAYMENT"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> JSONResponse:
        """Paid Assurance Report (x402 exact scheme over USDC).

        No payment -> 402 with requirements. Valid payment -> 200 with the
        signed report. Reused nonce -> 409 (or the original report on an
        idempotent retry carrying the same Idempotency-Key).
        """
        if not resolved.audit_hmac_key:
            raise HTTPException(status_code=503, detail="audit log not configured")
        if not resolved.reporting_signing_key:
            raise HTTPException(status_code=503, detail="reporting key not configured")
        if not resolved.x402_pay_to:
            raise HTTPException(status_code=503, detail="x402 payTo address not configured")

        requirements = build_payment_requirements(
            network=resolved.network,
            pay_to=resolved.x402_pay_to,
            price_atomic=usdc_atomic(resolved.x402_report_price_usdc),
            resource="/api/x402/assurance-report",
            description=f"NAPG Assurance Report for {body.protocol}",
        )

        if not x_payment:
            return JSONResponse(status_code=402, content=payment_required_body(requirements))

        def settle() -> tuple[dict[str, Any], int]:
            now = int(time.time())
            try:
                authorization, signature = decode_payment_header(x_payment)
                verified = verify_payment(authorization, signature, requirements, now=now)
            except X402Error as exc:
                return payment_required_body(requirements, error=exc.reason), 402
            window = ReportWindow(start_ts=now - body.window_seconds, end_ts=now)
            signer = ReportSigner.from_settings(resolved)
            with AuditLog(resolved.audit_db_path, resolved.audit_hmac_key) as log:
                try:
                    report, _ = settle_and_issue(
                        log,
                        signer,
                        verified,
                        protocol=body.protocol,
                        window=window,
                        generated_at=float(now),
                        idempotency_key=idempotency_key,
                    )
                except X402Error as exc:
                    return {"error": exc.reason}, 409
            return report.model_dump(mode="json"), 200

        content, status = await asyncio.to_thread(settle)
        return JSONResponse(status_code=status, content=content)

    @app.get("/api/guardian/status", response_model=GuardianStatus)
    async def guardian_status(fid: int = Query(ge=0)) -> GuardianStatus:
        """Guardian Mode entitlement for `fid`, decided from the audit log only.

        No request input other than the fid is consulted — a forged entitlement
        claim (header or body) cannot grant access; the audit log is the sole
        source of truth.
        """
        if not resolved.audit_hmac_key:
            raise HTTPException(status_code=503, detail="audit log not configured")

        def read_status() -> GuardianStatus:
            with AuditLog(resolved.audit_db_path, resolved.audit_hmac_key) as log:
                return entitlement_status(log, fid, now=time.time())

        return await asyncio.to_thread(read_status)

    return app


__all__ = ["CardError", "StatusResponse", "create_app"]


# The `napg serve` CLI imports this for uvicorn's `--factory` mode.
def _factory() -> Any:
    return create_app()
