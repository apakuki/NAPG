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
    base_rpc_url: str | None = Field(default=None, alias="BASE_RPC_URL")
    zerox_api_key: str | None = Field(default=None, alias="ZEROX_API_KEY")
    audit_db_path: str = Field(default="./audit.db", alias="NAPG_AUDIT_DB")

    @field_validator("base_sepolia_rpc_url", "base_rpc_url")
    @classmethod
    def _require_https(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not value.startswith("https://"):
            raise ValueError("RPC URL must use https:// (plaintext endpoints are rejected)")
        return value

    def active_rpc_url(self) -> str:
        url = self.base_rpc_url if self.network == "base-mainnet" else self.base_sepolia_rpc_url
        if not url:
            raise RuntimeError(
                f"No RPC URL configured for network={self.network}. "
                "Set BASE_SEPOLIA_RPC_URL or BASE_RPC_URL in .env."
            )
        return url
