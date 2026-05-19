"""Lending-market state poller for Morpho Blue on Base mainnet.

Originally PLAN.md substep 3 named Seamless as the target, but Seamless
announced an orderly wind-down in April 2026 (web app offline 2026-06-30).
By Phase 1 ship date there would be no Seamless to monitor. We repointed
to Morpho because Coinbase Loans on Base runs on Morpho Blue, making it
the largest load-bearing lending surface NAPG could plausibly watch.

Morpho Blue is structurally different from Aave v3:
- One singleton contract holds every market; markets are addressed by
  `bytes32 id` derived from (loanToken, collateralToken, oracle, irm, lltv).
- There is no per-asset "Pool" with aggregate reserve state. Each market
  is its own balance sheet: borrow USDC against WETH and borrow USDC
  against cbBTC are entirely separate markets.

This probe reads two market state structs per tick and reports
utilisation, supply/borrow assets, and how stale the on-chain accrual
state is. Oracle-freshness checking (the second half of PLAN.md
substep 3) is deferred to a follow-up commit because Morpho oracles
are arbitrary `IOracle` contracts and need per-market introspection
rather than a single shared `AaveOracle.getSourceOfAsset` lookup.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from web3 import Web3

MORPHO_BLUE_BASE = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
BASE_CHAIN_ID = 8453

USDC_BASE_MAINNET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
WETH_BASE_MAINNET = "0x4200000000000000000000000000000000000006"
CBBTC_BASE_MAINNET = "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf"

# Market IDs sourced from app.morpho.org URLs. Both markets borrow USDC.
# WETH-USDC is the largest general-purpose Morpho market on Base; cbBTC-USDC
# is the market that powers Coinbase Loans (more than $1.4B of cbBTC
# collateral as of mid-2026).
WETH_USDC_MARKET_ID = "0x8793cf302b8ffd655ab97bd1c695dbd967807e8367a65cb2f4edaf1380ba1bda"
CBBTC_USDC_MARKET_ID = "0x9103c3b4e834476c9a62ea009ba2c884ee42e94e6e314a26f04d312434191836"


MORPHO_BLUE_ABI: list[dict[str, Any]] = [
    {
        "name": "market",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "id", "type": "bytes32"}],
        "outputs": [
            {"name": "totalSupplyAssets", "type": "uint128"},
            {"name": "totalSupplyShares", "type": "uint128"},
            {"name": "totalBorrowAssets", "type": "uint128"},
            {"name": "totalBorrowShares", "type": "uint128"},
            {"name": "lastUpdate", "type": "uint128"},
            {"name": "fee", "type": "uint128"},
        ],
    },
]


class MarketTarget(BaseModel):
    """Static description of a market we monitor (human-readable labels)."""

    model_config = ConfigDict(frozen=True)

    label: str
    market_id: str
    loan_token: str
    loan_symbol: str
    collateral_token: str
    collateral_symbol: str


DEFAULT_TARGETS: tuple[MarketTarget, ...] = (
    MarketTarget(
        label="WETH-USDC",
        market_id=WETH_USDC_MARKET_ID,
        loan_token=USDC_BASE_MAINNET,
        loan_symbol="USDC",
        collateral_token=WETH_BASE_MAINNET,
        collateral_symbol="WETH",
    ),
    MarketTarget(
        label="cbBTC-USDC",
        market_id=CBBTC_USDC_MARKET_ID,
        loan_token=USDC_BASE_MAINNET,
        loan_symbol="USDC",
        collateral_token=CBBTC_BASE_MAINNET,
        collateral_symbol="cbBTC",
    ),
)


class MarketState(BaseModel):
    """One tick of a single Morpho Blue market on Base mainnet."""

    model_config = ConfigDict(frozen=True)

    label: str
    market_id: str
    loan_symbol: str
    collateral_symbol: str
    total_supply_assets: int = Field(ge=0)
    total_borrow_assets: int = Field(ge=0)
    utilization_bps: int = Field(ge=0, le=10_000)
    last_update: int = Field(ge=0)
    staleness_seconds: int = Field(ge=0)
    block_number: int = Field(ge=0)
    observed_at: float


class MorphoPoll(BaseModel):
    """A full tick: every monitored market plus the block we read at."""

    model_config = ConfigDict(frozen=True)

    chain_id: int
    block_number: int
    block_timestamp: int
    markets: tuple[MarketState, ...]
    latency_ms: float = Field(ge=0)
    observed_at: float


class MorphoMonitor:
    """Reads Morpho Blue market state via Web3.py against a Base mainnet RPC.

    Inject a `Web3` instance to mock in tests.
    """

    def __init__(
        self,
        rpc_url: str,
        web3: Web3 | None = None,
        targets: Sequence[MarketTarget] = DEFAULT_TARGETS,
    ) -> None:
        if not rpc_url.startswith("https://"):
            raise ValueError("RPC URL must use https://")
        if not targets:
            raise ValueError("at least one market target is required")
        self.rpc_url = rpc_url
        self._web3 = web3 if web3 is not None else Web3(Web3.HTTPProvider(rpc_url))
        self._targets = tuple(targets)
        self._contract = self._web3.eth.contract(
            address=Web3.to_checksum_address(MORPHO_BLUE_BASE),
            abi=MORPHO_BLUE_ABI,
        )

    @property
    def targets(self) -> tuple[MarketTarget, ...]:
        return self._targets

    def tick(self) -> MorphoPoll:
        start = time.perf_counter()
        latest = self._web3.eth.get_block("latest")
        block_number = int(latest["number"])
        block_timestamp = int(latest["timestamp"])

        markets: list[MarketState] = []
        for target in self._targets:
            raw = self._contract.functions.market(_to_bytes32(target.market_id)).call()
            markets.append(
                _build_market_state(
                    target=target,
                    raw=raw,
                    block_number=block_number,
                    block_timestamp=block_timestamp,
                )
            )

        latency_ms = (time.perf_counter() - start) * 1000.0
        return MorphoPoll(
            chain_id=BASE_CHAIN_ID,
            block_number=block_number,
            block_timestamp=block_timestamp,
            markets=tuple(markets),
            latency_ms=latency_ms,
            observed_at=time.time(),
        )


def _to_bytes32(value: str) -> bytes:
    """Accept '0x...' hex and return 32 raw bytes. Rejects wrong length."""
    if not value.startswith("0x"):
        raise ValueError(f"market id must be 0x-prefixed hex: {value!r}")
    raw = bytes.fromhex(value[2:])
    if len(raw) != 32:
        raise ValueError(f"market id must decode to 32 bytes, got {len(raw)}: {value!r}")
    return raw


def _build_market_state(
    target: MarketTarget,
    raw: Sequence[int],
    block_number: int,
    block_timestamp: int,
) -> MarketState:
    total_supply_assets = int(raw[0])
    total_borrow_assets = int(raw[2])
    last_update = int(raw[4])

    utilization_bps = 0
    if total_supply_assets > 0:
        utilization_bps = round(total_borrow_assets * 10_000 / total_supply_assets)
        if utilization_bps > 10_000:
            utilization_bps = 10_000

    staleness = max(0, block_timestamp - last_update)

    return MarketState(
        label=target.label,
        market_id=target.market_id,
        loan_symbol=target.loan_symbol,
        collateral_symbol=target.collateral_symbol,
        total_supply_assets=total_supply_assets,
        total_borrow_assets=total_borrow_assets,
        utilization_bps=utilization_bps,
        last_update=last_update,
        staleness_seconds=staleness,
        block_number=block_number,
        observed_at=time.time(),
    )


__all__ = [
    "BASE_CHAIN_ID",
    "CBBTC_USDC_MARKET_ID",
    "DEFAULT_TARGETS",
    "MORPHO_BLUE_BASE",
    "WETH_USDC_MARKET_ID",
    "MarketState",
    "MarketTarget",
    "MorphoMonitor",
    "MorphoPoll",
]
