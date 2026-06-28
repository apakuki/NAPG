"""Runtime configuration loaded from environment / .env.

Single source of truth for which network the agent runs against and which RPC
endpoints it is allowed to use. HTTPS-only by construction: an `http://` URL is
rejected at load time so no monitor can accidentally point at a plaintext
endpoint.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Network = Literal["base-sepolia", "base-mainnet"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Look in the agent/ working dir first, then the repo root one level up.
        # Later entries override earlier ones in pydantic-settings.
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    network: Network = Field(default="base-sepolia", alias="NAPG_NETWORK")
    base_sepolia_rpc_url: str | None = Field(default=None, alias="BASE_SEPOLIA_RPC_URL")
    base_sepolia_rpc_url_fallback: str | None = Field(
        default=None, alias="BASE_SEPOLIA_RPC_URL_FALLBACK"
    )
    base_rpc_url: str | None = Field(default=None, alias="BASE_RPC_URL")
    base_rpc_url_fallback: str | None = Field(default=None, alias="BASE_RPC_URL_FALLBACK")
    zerox_api_key: str | None = Field(default=None, alias="ZEROX_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    # Model split for failure independence (hardening decision 6): the planner
    # (Reasoner) and the Stage 1 Intent Judge run on *different* Claude models so
    # they do not share a single failure mode. Stage 2 (deterministic) remains the
    # real backstop regardless. Both stay within the locked Anthropic-only stack.
    reasoner_model: str = Field(default="claude-opus-4-8", alias="NAPG_REASONER_MODEL")
    intent_judge_model: str = Field(
        default="claude-haiku-4-5-20251001", alias="NAPG_INTENT_JUDGE_MODEL"
    )
    cdp_api_key_name: str | None = Field(default=None, alias="CDP_API_KEY_NAME")
    cdp_api_key_private_key: str | None = Field(default=None, alias="CDP_API_KEY_PRIVATE_KEY")
    cdp_wallet_secret: str | None = Field(default=None, alias="CDP_WALLET_SECRET")
    cdp_agent_address: str | None = Field(default=None, alias="CDP_AGENT_ADDRESS")
    safe_contract_address: str | None = Field(default=None, alias="NAPG_SAFE_CONTRACT_ADDRESS")
    audit_db_path: str = Field(default="./audit.db", alias="NAPG_AUDIT_DB")
    audit_hmac_key: str | None = Field(default=None, alias="NAPG_AUDIT_HMAC_KEY")
    # Dedicated Assurance Report signing key (Ed25519 32-byte seed, hex). Kept
    # distinct from the operational MPC wallet key; never written to the audit
    # DB. Generate with `napg report generate-key`.
    reporting_signing_key: str | None = Field(default=None, alias="NAPG_REPORTING_SIGNING_KEY")
    # x402 paid-report surface. `x402_pay_to` is the address that receives USDC
    # for Assurance Reports; without it the endpoint cannot accept payment.
    x402_pay_to: str | None = Field(default=None, alias="NAPG_X402_PAY_TO")
    x402_report_price_usdc: str = Field(default="0.10", alias="NAPG_X402_REPORT_PRICE_USDC")
    # ERC-8021 Builder Code for sequencer-reward attribution. When set, every
    # NAPG-originated tx carries this code as a calldata suffix (via
    # napg.attribution). Registered on Base.dev; unset until then.
    builder_code: str | None = Field(default=None, alias="NAPG_BUILDER_CODE")
    tenderly_account_slug: str | None = Field(default=None, alias="TENDERLY_ACCOUNT_SLUG")
    tenderly_project_slug: str | None = Field(default=None, alias="TENDERLY_PROJECT_SLUG")
    tenderly_access_key: str | None = Field(default=None, alias="TENDERLY_ACCESS_KEY")

    @field_validator(
        "base_sepolia_rpc_url",
        "base_sepolia_rpc_url_fallback",
        "base_rpc_url",
        "base_rpc_url_fallback",
    )
    @classmethod
    def _require_https(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not value.startswith("https://"):
            raise ValueError("RPC URL must use https:// (plaintext endpoints are rejected)")
        return value

    def active_rpc_url(self) -> str:
        return self.active_rpc_urls()[0]

    def active_rpc_urls(self) -> tuple[str, ...]:
        """Return (primary, fallback?) for the active network. Primary required."""
        if self.network == "base-mainnet":
            primary, fallback = self.base_rpc_url, self.base_rpc_url_fallback
            env_hint = "BASE_RPC_URL"
        else:
            primary, fallback = self.base_sepolia_rpc_url, self.base_sepolia_rpc_url_fallback
            env_hint = "BASE_SEPOLIA_RPC_URL"
        if not primary:
            raise RuntimeError(
                f"No RPC URL configured for network={self.network}. Set {env_hint} in .env."
            )
        return (primary, fallback) if fallback else (primary,)
