"""Tests for napg.config — env loading and HTTPS guard."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from napg.config import Settings


def _settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[call-arg]


def test_https_url_accepted():
    s = _settings(BASE_SEPOLIA_RPC_URL="https://sepolia.example/rpc")
    assert s.base_sepolia_rpc_url == "https://sepolia.example/rpc"


def test_http_url_rejected():
    with pytest.raises(ValidationError, match="https"):
        _settings(BASE_SEPOLIA_RPC_URL="http://insecure.example/rpc")


def test_blank_url_treated_as_unset():
    s = _settings(BASE_SEPOLIA_RPC_URL="")
    assert s.base_sepolia_rpc_url is None


def test_default_network_is_sepolia():
    s = _settings()
    assert s.network == "base-sepolia"


def test_active_rpc_url_picks_network():
    sepolia = _settings(
        NAPG_NETWORK="base-sepolia",
        BASE_SEPOLIA_RPC_URL="https://sepolia.example/rpc",
        BASE_RPC_URL="https://mainnet.example/rpc",
    )
    assert sepolia.active_rpc_url() == "https://sepolia.example/rpc"

    mainnet = _settings(
        NAPG_NETWORK="base-mainnet",
        BASE_SEPOLIA_RPC_URL="https://sepolia.example/rpc",
        BASE_RPC_URL="https://mainnet.example/rpc",
    )
    assert mainnet.active_rpc_url() == "https://mainnet.example/rpc"


def test_active_rpc_url_raises_when_unset():
    s = _settings(NAPG_NETWORK="base-sepolia")
    with pytest.raises(RuntimeError, match="No RPC URL configured"):
        s.active_rpc_url()


def test_active_rpc_urls_returns_only_primary_when_no_fallback():
    s = _settings(
        NAPG_NETWORK="base-sepolia",
        BASE_SEPOLIA_RPC_URL="https://sepolia.example/rpc",
    )
    assert s.active_rpc_urls() == ("https://sepolia.example/rpc",)


def test_active_rpc_urls_includes_fallback_when_set():
    s = _settings(
        NAPG_NETWORK="base-sepolia",
        BASE_SEPOLIA_RPC_URL="https://primary.example/rpc",
        BASE_SEPOLIA_RPC_URL_FALLBACK="https://fallback.example/rpc",
    )
    assert s.active_rpc_urls() == (
        "https://primary.example/rpc",
        "https://fallback.example/rpc",
    )


def test_fallback_url_must_also_be_https():
    with pytest.raises(ValidationError, match="https"):
        _settings(BASE_SEPOLIA_RPC_URL_FALLBACK="http://fallback.example/rpc")
