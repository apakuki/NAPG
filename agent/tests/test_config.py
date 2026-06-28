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


def test_reporting_signing_key_loads_from_env():
    s = _settings(NAPG_REPORTING_SIGNING_KEY="ab" * 32)
    assert s.reporting_signing_key == "ab" * 32


def test_reporting_signing_key_defaults_to_none():
    assert _settings().reporting_signing_key is None


def test_builder_code_loads_from_env_and_defaults_to_none():
    assert _settings().builder_code is None
    assert _settings(NAPG_BUILDER_CODE="napg").builder_code == "napg"


def test_reasoner_and_judge_models_are_different_by_default():
    """Failure independence (hardening decision 6): planner and Intent Judge must
    default to different Claude models, both within the Anthropic stack."""
    s = _settings()
    assert s.reasoner_model == "claude-opus-4-8"
    assert s.intent_judge_model == "claude-haiku-4-5-20251001"
    assert s.reasoner_model != s.intent_judge_model


def test_models_override_from_env():
    s = _settings(
        NAPG_REASONER_MODEL="claude-opus-4-8", NAPG_INTENT_JUDGE_MODEL="claude-sonnet-4-6"
    )
    assert s.intent_judge_model == "claude-sonnet-4-6"
