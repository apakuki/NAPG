"""Unit tests for napg.wallet — env-driven config plumbing into AgentKit."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from napg.config import Settings
from napg.wallet import build_agent_wallet


def _settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[call-arg]


def test_missing_api_key_name_raises() -> None:
    settings = _settings(
        CDP_API_KEY_PRIVATE_KEY="secret",
        CDP_WALLET_SECRET="wallet",
    )
    with pytest.raises(RuntimeError, match="CDP_API_KEY_NAME"):
        build_agent_wallet(settings)


def test_missing_api_key_private_key_raises() -> None:
    settings = _settings(
        CDP_API_KEY_NAME="name",
        CDP_WALLET_SECRET="wallet",
    )
    with pytest.raises(RuntimeError, match="CDP_API_KEY_PRIVATE_KEY"):
        build_agent_wallet(settings)


def test_missing_wallet_secret_raises_with_portal_hint() -> None:
    settings = _settings(
        CDP_API_KEY_NAME="name",
        CDP_API_KEY_PRIVATE_KEY="secret",
    )
    with pytest.raises(RuntimeError, match="CDP_WALLET_SECRET"):
        build_agent_wallet(settings)


def test_factory_passes_credentials_through_to_provider() -> None:
    settings = _settings(
        CDP_API_KEY_NAME="key-name",
        CDP_API_KEY_PRIVATE_KEY="key-secret",
        CDP_WALLET_SECRET="wallet-secret",
        CDP_AGENT_ADDRESS="0x" + "ab" * 20,
        NAPG_NETWORK="base-sepolia",
    )

    fake_provider = MagicMock()
    captured: dict[str, object] = {}

    def fake_init(config):
        captured["config"] = config
        return fake_provider

    with patch("napg.wallet.CdpEvmWalletProvider", side_effect=fake_init):
        result = build_agent_wallet(settings)

    assert result is fake_provider
    cfg = captured["config"]
    assert cfg.api_key_id == "key-name"
    assert cfg.api_key_secret == "key-secret"
    assert cfg.wallet_secret == "wallet-secret"
    assert cfg.network_id == "base-sepolia"
    assert cfg.address == "0x" + "ab" * 20


def test_blank_agent_address_maps_to_none() -> None:
    """An empty CDP_AGENT_ADDRESS must NOT be passed through as ""."""
    settings = _settings(
        CDP_API_KEY_NAME="key-name",
        CDP_API_KEY_PRIVATE_KEY="key-secret",
        CDP_WALLET_SECRET="wallet-secret",
        CDP_AGENT_ADDRESS="",
    )
    captured: dict[str, object] = {}

    def fake_init(config):
        captured["config"] = config
        return MagicMock()

    with patch("napg.wallet.CdpEvmWalletProvider", side_effect=fake_init):
        build_agent_wallet(settings)

    cfg = captured["config"]
    assert cfg.address is None


def test_mainnet_network_id_passes_through() -> None:
    settings = _settings(
        CDP_API_KEY_NAME="key-name",
        CDP_API_KEY_PRIVATE_KEY="key-secret",
        CDP_WALLET_SECRET="wallet-secret",
        NAPG_NETWORK="base-mainnet",
    )
    captured: dict[str, object] = {}

    def fake_init(config):
        captured["config"] = config
        return MagicMock()

    with patch("napg.wallet.CdpEvmWalletProvider", side_effect=fake_init):
        build_agent_wallet(settings)

    assert captured["config"].network_id == "base-mainnet"
