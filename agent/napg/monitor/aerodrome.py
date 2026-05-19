"""Liquidity probe for the Aerodrome USDT/USDC stable pool via the 0x API.

The 0x v2 aggregator routes through whichever source clears at the best price,
so a single probe reports the market-clearing USDC/USDT rate for the entire
Base ecosystem and lists which sources actually filled. For peg-deviation
monitoring this is more useful than a single-pool read: if Aerodrome routes,
we surveil it; if not, the absence of Aerodrome in the route is itself signal
(depeg, drained liquidity, or fee/spread regression).

The probed pair is USDC/USDT, not USDC/USDbC: USDbC (Coinbase Bridged USDC) has
been in wind-down since Circle deployed native USDC on Base in September 2023,
and the Aerodrome USDC/USDbC pool no longer carries meaningful TVL. USDT/USDC
is currently Aerodrome's deepest stable/stable pool, which is the surface a
Protocol Service Assurance probe should actually be watching.

Aerodrome lives on Base mainnet only, so this probe always queries chainId
8453 regardless of the agent's configured execution network.
"""

from __future__ import annotations

import time

import httpx
from pydantic import BaseModel, ConfigDict, Field

USDC_BASE_MAINNET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDT_BASE_MAINNET = "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2"
BASE_CHAIN_ID = 8453
ZEROX_PRICE_URL = "https://api.0x.org/swap/permit2/price"
ZEROX_API_VERSION = "v2"

DEFAULT_PROBE_AMOUNT_USDC = 10_000 * 10**6


class ZeroExFill(BaseModel):
    """One leg of a 0x routed swap. We care about source + share."""

    model_config = ConfigDict(extra="ignore")

    source: str
    proportion_bps: int = Field(alias="proportionBps")


class ZeroExRoute(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fills: list[ZeroExFill] = Field(default_factory=list)


class ZeroExPriceResponse(BaseModel):
    """Subset of the 0x /swap/permit2/price response we depend on.

    `extra=ignore` so 0x can add fields without breaking the probe.
    """

    model_config = ConfigDict(extra="ignore")

    liquidity_available: bool = Field(alias="liquidityAvailable")
    block_number: int | None = Field(default=None, alias="blockNumber")
    sell_amount: int | None = Field(default=None, alias="sellAmount")
    buy_amount: int | None = Field(default=None, alias="buyAmount")
    min_buy_amount: int | None = Field(default=None, alias="minBuyAmount")
    route: ZeroExRoute | None = None


class LiquidityProbe(BaseModel):
    """One Aerodrome probe tick: quoted rate, peg deviation, routing context.

    `peg_deviation_bps` is `abs(quoted_rate - 1.0) * 10_000`, defined only when
    a quote came back. The agent uses this to evaluate a "peg drop" service
    level breach (Phase 1 substep 4).
    """

    model_config = ConfigDict(frozen=True)

    chain_id: int
    sell_token: str
    buy_token: str
    sell_amount: int = Field(ge=0)
    buy_amount: int = Field(ge=0)
    liquidity_available: bool
    quoted_rate: float | None = None
    peg_deviation_bps: int | None = None
    sources: tuple[str, ...] = ()
    block_number: int | None = None
    latency_ms: float = Field(ge=0)
    observed_at: float


class AerodromeMonitor:
    """0x-backed probe for USDC/USDT liquidity on Base mainnet.

    Inject an `httpx.Client` to mock in tests via `httpx.MockTransport`.
    """

    def __init__(
        self,
        api_key: str,
        http: httpx.Client | None = None,
        sell_token: str = USDC_BASE_MAINNET,
        buy_token: str = USDT_BASE_MAINNET,
        sell_amount: int = DEFAULT_PROBE_AMOUNT_USDC,
        timeout: float = 5.0,
    ) -> None:
        if not api_key:
            raise ValueError("0x API key is required (set ZEROX_API_KEY in .env)")
        if sell_amount <= 0:
            raise ValueError("sell_amount must be positive")
        self._api_key = api_key
        self._sell_token = sell_token
        self._buy_token = buy_token
        self._sell_amount = sell_amount
        self._http = http if http is not None else httpx.Client(timeout=timeout)

    def tick(self) -> LiquidityProbe:
        params = {
            "chainId": BASE_CHAIN_ID,
            "sellToken": self._sell_token,
            "buyToken": self._buy_token,
            "sellAmount": str(self._sell_amount),
        }
        headers = {"0x-api-key": self._api_key, "0x-version": ZEROX_API_VERSION}

        start = time.perf_counter()
        response = self._http.get(ZEROX_PRICE_URL, params=params, headers=headers)
        latency_ms = (time.perf_counter() - start) * 1000.0

        if response.status_code != 200:
            raise RuntimeError(
                f"0x price API returned {response.status_code}: {response.text[:200]}"
            )

        parsed = ZeroExPriceResponse.model_validate(response.json())
        return _build_probe(
            parsed=parsed,
            chain_id=BASE_CHAIN_ID,
            sell_token=self._sell_token,
            buy_token=self._buy_token,
            requested_sell_amount=self._sell_amount,
            latency_ms=latency_ms,
        )


def _build_probe(
    parsed: ZeroExPriceResponse,
    chain_id: int,
    sell_token: str,
    buy_token: str,
    requested_sell_amount: int,
    latency_ms: float,
) -> LiquidityProbe:
    sell_amount = parsed.sell_amount if parsed.sell_amount is not None else requested_sell_amount
    buy_amount = parsed.buy_amount or 0
    sources = tuple(fill.source for fill in (parsed.route.fills if parsed.route else []))

    quoted_rate: float | None = None
    peg_deviation_bps: int | None = None
    if parsed.liquidity_available and sell_amount > 0 and buy_amount > 0:
        quoted_rate = buy_amount / sell_amount
        peg_deviation_bps = round(abs(quoted_rate - 1.0) * 10_000)

    return LiquidityProbe(
        chain_id=chain_id,
        sell_token=sell_token,
        buy_token=buy_token,
        sell_amount=sell_amount,
        buy_amount=buy_amount,
        liquidity_available=parsed.liquidity_available,
        quoted_rate=quoted_rate,
        peg_deviation_bps=peg_deviation_bps,
        sources=sources,
        block_number=parsed.block_number,
        latency_ms=latency_ms,
        observed_at=time.time(),
    )


__all__ = [
    "BASE_CHAIN_ID",
    "DEFAULT_PROBE_AMOUNT_USDC",
    "USDC_BASE_MAINNET",
    "USDT_BASE_MAINNET",
    "AerodromeMonitor",
    "LiquidityProbe",
]
