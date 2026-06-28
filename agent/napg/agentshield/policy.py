"""Signed policy + denylist config loaders for AgentShield Stage 2.

The policy file controls Stage 2 (Policy Validation): per-tx caps, token
allowlist, destination allowlist, daily-spend ceiling. The denylist file
holds known-bad destination addresses. Phase 2 ships a small static
denylist; the long-term shape is a signed feed.

Both files are Ed25519-signed by a private key held outside the repo
(default at `~/.napg/policy_signing_key.pem`). The matching public key
sits at `agent/config/policy_public_key.pem`. The loader verifies the
signature against the public key before parsing — unsigned or
mismatched-signature configs are rejected with a clear error.

Signature format: detached Ed25519 signature over the raw bytes of the
config file, written to `<config>.sig` alongside it.

CLI helpers in `napg.__main__`:
- `napg policy generate-key` — creates `~/.napg/policy_signing_key.pem`
  and writes the corresponding public key to
  `agent/config/policy_public_key.pem`.
- `napg policy sign <path>` — signs the file using the configured
  private key, writes `<path>.sig`.
- `napg policy verify <path>` — verifies the file's signature against
  the configured public key.

Tests inject paths via `tmp_path` and build a fresh keypair each test
so they do not depend on filesystem state from a prior CLI invocation.
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.10 fallback path
    import tomli as tomllib  # type: ignore[no-redef]

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

_HEX_ADDRESS_LEN = 42


def _normalize_addresses(value: object, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise ValueError(f"{field_name} must be a list of 0x... strings")
    normalized: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            raise ValueError(f"{field_name} entries must be strings, got {type(entry).__name__}")
        if not entry.startswith("0x") or len(entry) != _HEX_ADDRESS_LEN:
            raise ValueError(f"not a 20-byte 0x-hex address: {entry!r}")
        normalized.append(entry.lower())
    return tuple(normalized)


class PolicyConfig(BaseModel):
    """Phase 2 policy: per-tx caps, allowlists, daily ceiling."""

    model_config = ConfigDict(frozen=True)

    max_value_wei_per_tx: int = Field(ge=0)
    daily_spend_cap_wei: int = Field(ge=0)
    # Group E MEV gate. Maximum tolerated slippage on a swap intent, in basis
    # points: a swap whose min_out implies more than this slippage off the quote
    # fails closed. Default 50 (0.5%) per kickoff decision 3.
    max_slippage_bps: int = Field(default=50, ge=0, le=10_000)
    # Maximum age (seconds) of a Stage 3 simulation at signing time. Beyond this
    # the market may have moved between sim and inclusion; re-simulate rather than
    # sign stale. Default 5s per the hardening review.
    max_simulation_age_seconds: float = Field(default=5.0, ge=0)
    # Empty allowlist = no token-allowlist check (native ETH only is enforced by
    # the calldata check in Stage 2). Non-empty list reserves space for ERC-20
    # allowlisting when calldata decoding lands.
    token_allowlist: tuple[str, ...] = ()
    # Empty allowlist = no destination check (any destination allowed). Non-
    # empty list restricts destinations to exactly those addresses.
    destination_allowlist: tuple[str, ...] = ()
    # Group E swap token universe. A swap's token_in AND token_out must both be
    # on this list. Empty (the default) = no swap tokens allowed = every swap
    # fails closed, which matches the transfer-only launch posture. Populate
    # with a constrained set (USDC / USDT / cbBTC / WETH) when enabling swaps;
    # keep fee-on-transfer / rebasing / exotic tokens off it.
    swap_token_allowlist: tuple[str, ...] = ()

    @field_validator("token_allowlist", mode="before")
    @classmethod
    def _normalize_tokens(cls, value: object) -> tuple[str, ...]:
        return _normalize_addresses(value, "token_allowlist")

    @field_validator("destination_allowlist", mode="before")
    @classmethod
    def _normalize_destinations(cls, value: object) -> tuple[str, ...]:
        return _normalize_addresses(value, "destination_allowlist")

    @field_validator("swap_token_allowlist", mode="before")
    @classmethod
    def _normalize_swap_tokens(cls, value: object) -> tuple[str, ...]:
        return _normalize_addresses(value, "swap_token_allowlist")


class Denylist(BaseModel):
    """Static list of denied destination addresses for Stage 2."""

    model_config = ConfigDict(frozen=True)

    addresses: tuple[str, ...] = ()

    @field_validator("addresses", mode="before")
    @classmethod
    def _normalize(cls, value: object) -> tuple[str, ...]:
        return _normalize_addresses(value, "addresses")

    def contains(self, address: str) -> bool:
        return address.lower() in self.addresses


def sig_path_for(config_path: Path) -> Path:
    """Detached signature lives next to the config as `<config>.sig`."""
    return config_path.with_name(config_path.name + ".sig")


def _verify_signature(config_bytes: bytes, signature: bytes, public_key_pem: bytes) -> None:
    """Verify Ed25519 signature over the raw config bytes. Raises on mismatch."""
    key = serialization.load_pem_public_key(public_key_pem)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("policy public key must be Ed25519")
    try:
        key.verify(signature, config_bytes)
    except InvalidSignature as exc:
        raise ValueError("policy config signature did not verify against the public key") from exc


def _read_signed_config(config_path: Path, public_key_path: Path) -> bytes:
    """Verify signature and return the raw config bytes for parsing."""
    sig_path = sig_path_for(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"missing config file: {config_path}")
    if not sig_path.exists():
        raise FileNotFoundError(
            f"missing signature file: {sig_path} "
            f"(sign with `napg policy sign {config_path}` before loading)"
        )
    if not public_key_path.exists():
        raise FileNotFoundError(
            f"missing public key: {public_key_path} "
            "(generate with `napg policy generate-key` before loading)"
        )
    config_bytes = config_path.read_bytes()
    signature = sig_path.read_bytes()
    public_key_pem = public_key_path.read_bytes()
    _verify_signature(config_bytes, signature, public_key_pem)
    return config_bytes


def load_policy(config_path: Path, public_key_path: Path) -> PolicyConfig:
    """Verify the signature on `config_path` and return the parsed policy."""
    config_bytes = _read_signed_config(config_path, public_key_path)
    data = tomllib.loads(config_bytes.decode("utf-8"))
    return PolicyConfig.model_validate(data)


def load_denylist(config_path: Path, public_key_path: Path) -> Denylist:
    """Verify the signature on `config_path` and return the parsed denylist."""
    config_bytes = _read_signed_config(config_path, public_key_path)
    data = tomllib.loads(config_bytes.decode("utf-8"))
    return Denylist.model_validate(data)


def sign_file(config_path: Path, private_key_path: Path) -> Path:
    """Sign `config_path` using `private_key_path`. Writes `<config>.sig`."""
    if not config_path.exists():
        raise FileNotFoundError(f"missing config file: {config_path}")
    if not private_key_path.exists():
        raise FileNotFoundError(
            f"missing private key: {private_key_path} "
            "(generate with `napg policy generate-key` first)"
        )
    pem = private_key_path.read_bytes()
    private_key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("policy signing key must be Ed25519")
    signature = private_key.sign(config_path.read_bytes())
    sig_path = sig_path_for(config_path)
    sig_path.write_bytes(signature)
    return sig_path


def verify_file(config_path: Path, public_key_path: Path) -> bool:
    """Verify the signature on `config_path`. Returns True or raises ValueError."""
    _read_signed_config(config_path, public_key_path)
    return True


def generate_keypair() -> tuple[bytes, bytes]:
    """Return (private_pem, public_pem) for a fresh Ed25519 keypair.

    Used by `napg policy generate-key`; tests use it to build per-test
    keypairs without touching the user's `~/.napg/` directory.
    """
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def default_private_key_path() -> Path:
    """`~/.napg/policy_signing_key.pem`. Lives outside the repo."""
    return Path.home() / ".napg" / "policy_signing_key.pem"


def default_public_key_path() -> Path:
    """`agent/config/policy_public_key.pem`. Committed to the repo."""
    return Path(__file__).resolve().parents[2] / "config" / "policy_public_key.pem"


def default_policy_path() -> Path:
    """`agent/config/policy.toml`. Committed to the repo."""
    return Path(__file__).resolve().parents[2] / "config" / "policy.toml"


def default_denylist_path() -> Path:
    """`agent/config/denylist.toml`. Committed to the repo."""
    return Path(__file__).resolve().parents[2] / "config" / "denylist.toml"


__all__ = [
    "Denylist",
    "PolicyConfig",
    "default_denylist_path",
    "default_policy_path",
    "default_private_key_path",
    "default_public_key_path",
    "generate_keypair",
    "load_denylist",
    "load_policy",
    "sig_path_for",
    "sign_file",
    "verify_file",
]
