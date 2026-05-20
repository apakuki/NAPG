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
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from napg.config import Settings
from napg.monitor.aerodrome import AerodromeMonitor, LiquidityProbe
from napg.monitor.morpho import MorphoMonitor, MorphoPoll
from napg.monitor.resilience import FailoverRpcHeartbeat
from napg.monitor.rpc import HeartbeatResult, RpcHeartbeat

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
        return AerodromeMonitor(api_key=settings.zerox_api_key).tick()
    except Exception as exc:
        logger.warning("aerodrome probe failed: %s", type(exc).__name__)
        return CardError(error=f"{type(exc).__name__}: {exc}")


def _morpho(settings: Settings) -> MorphoPoll | CardError:
    if not settings.base_rpc_url:
        return CardError(error="BASE_RPC_URL not set (Morpho needs Base mainnet)")
    try:
        return MorphoMonitor(settings.base_rpc_url).tick()
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

    return app


__all__ = ["CardError", "StatusResponse", "create_app"]


# The `napg serve` CLI imports this for uvicorn's `--factory` mode.
def _factory() -> Any:
    return create_app()
