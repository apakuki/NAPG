"""Agent wallet bootstrap on top of `coinbase-agentkit` CDP v2.

This is the only place NAPG touches the CDP SDK. Everything downstream
receives a `CdpEvmWalletProvider` instance and uses its narrow surface
(`get_address`, `get_balance`, `native_transfer`, `send_transaction`).

MPC-only by construction: the wallet keys live in CDP's TEE; we never see
private keys, mnemonics, or signed payloads in the agent process. The
`wallet_secret` env var is the only signing-control material we hold, and
it never lands in the audit DB (the audit-log unit tests enforce this).
"""

from __future__ import annotations

from typing import Literal

from coinbase_agentkit import CdpEvmWalletProvider, CdpEvmWalletProviderConfig

from napg.config import Settings

CdpNetwork = Literal["base-sepolia", "base-mainnet"]

# CDP's network_id strings happen to match our `NAPG_NETWORK` values
# 1:1 today; the mapping is explicit so a future divergence is obvious.
_NETWORK_MAP: dict[str, str] = {
    "base-sepolia": "base-sepolia",
    "base-mainnet": "base-mainnet",
}


def build_agent_wallet(settings: Settings) -> CdpEvmWalletProvider:
    """Construct the CDP-backed agent wallet from the loaded Settings.

    Raises a clear RuntimeError when any of the three required CDP secrets is
    missing — callers should not have to inspect Settings before calling this.
    """
    if not settings.cdp_api_key_name:
        raise RuntimeError("CDP_API_KEY_NAME is not set; populate .env before wallet ops.")
    if not settings.cdp_api_key_private_key:
        raise RuntimeError("CDP_API_KEY_PRIVATE_KEY is not set; populate .env before wallet ops.")
    if not settings.cdp_wallet_secret:
        raise RuntimeError(
            "CDP_WALLET_SECRET is not set. Generate one in the CDP portal "
            "(https://portal.cdp.coinbase.com/) alongside your API key; v2 wallets "
            "require it for server-side signing."
        )

    network_id = _NETWORK_MAP.get(settings.network)
    if network_id is None:
        raise RuntimeError(f"Unsupported network for CDP wallet: {settings.network!r}")

    config = CdpEvmWalletProviderConfig(
        api_key_id=settings.cdp_api_key_name,
        api_key_secret=settings.cdp_api_key_private_key,
        wallet_secret=settings.cdp_wallet_secret,
        network_id=network_id,
        address=settings.cdp_agent_address or None,
    )
    return CdpEvmWalletProvider(config)


__all__ = ["build_agent_wallet"]
