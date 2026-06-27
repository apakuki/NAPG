"""ERC-8021 Builder Code attribution: the single calldata-suffix helper.

Phase 4 Group C. ERC-8021 attributes a transaction to a builder by appending a
data suffix to its calldata. Smart contracts ignore extra data past their
function arguments, and EOAs ignore calldata entirely, so the suffix rides along
without affecting execution while an indexer reads it for reward attribution.

This module is the *only* place that constructs the suffix (enforced by a CI
grep test), so a Builder Code can never be set from user-controllable input and
every NAPG-originated tx carries the same, verifiable tag.

Suffix layout (schema 0 -- a single builder-code string), appended to the end of
the base calldata and parsed from the end backwards:

    [ schemaData ][ schemaId : 1 byte ][ ercMarker : 16 bytes ]

where for schema 0 the schemaData is a length-prefixed ASCII string:

    [ len : 1 byte ][ builder code : len bytes ]

Worked example from the Base docs for the code "baseapp":

    0x 07 62617365617070 00 80218021802180218021802180218021
       len "baseapp"      schema  ercMarker (0x8021 x8)

See https://docs.base.org/base-chain/builder-codes/builder-codes
"""

from __future__ import annotations

# 16-byte constant marker that ends every ERC-8021 data suffix.
ERC8021_MARKER = bytes.fromhex("80218021802180218021802180218021")
# Schema 0: a single length-prefixed ASCII builder code.
_SCHEMA_BUILDER_CODE = 0
_MAX_CODE_LEN = 255

_NATIVE_TRANSFER_CALLDATA = "0x"


def _encode_code(builder_code: str) -> bytes:
    """Validate and ASCII-encode a builder code. Raises ValueError on bad input."""
    if not builder_code:
        raise ValueError("builder code must be a non-empty ASCII string")
    try:
        code_bytes = builder_code.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("builder code must be ASCII-encodable") from exc
    if len(code_bytes) > _MAX_CODE_LEN:
        raise ValueError(f"builder code must be at most {_MAX_CODE_LEN} bytes")
    return code_bytes


def build_suffix(builder_code: str) -> str:
    """Return the 0x-hex ERC-8021 suffix for `builder_code` (schema 0)."""
    code_bytes = _encode_code(builder_code)
    suffix = bytes([len(code_bytes)]) + code_bytes + bytes([_SCHEMA_BUILDER_CODE]) + ERC8021_MARKER
    return "0x" + suffix.hex()


def append_suffix(base_calldata: str, builder_code: str) -> str:
    """Append the builder-code suffix to existing calldata.

    `base_calldata` is 0x-hex ("0x" for a native transfer). The suffix is the
    only thing appended; the base bytes are untouched.
    """
    if not base_calldata.startswith("0x"):
        raise ValueError("base_calldata must be 0x-hex")
    return base_calldata + build_suffix(builder_code).removeprefix("0x")


def is_attribution_only(data: str, builder_code: str | None) -> bool:
    """True iff `data` is exactly the suffix for `builder_code` on empty calldata.

    This is the fail-closed predicate the AgentShield stages use: it accepts a
    native transfer that carries *only* our attribution tag, and nothing else.
    Any other non-empty calldata (a contract call, an arbitrary blob, or a
    suffix for a different code) returns False so the stages keep blocking it.
    """
    if builder_code is None:
        return False
    return data.lower() == build_suffix(builder_code).lower()


def is_native_or_attribution(data: str, builder_code: str | None) -> bool:
    """True for a plain native transfer or a native transfer tagged with our
    builder code. The single 'is this effectively a native transfer?' check
    shared by Stage 2 (policy) and Stage 4 (honeypot)."""
    return data == _NATIVE_TRANSFER_CALLDATA or is_attribution_only(data, builder_code)


__all__ = [
    "ERC8021_MARKER",
    "append_suffix",
    "build_suffix",
    "is_attribution_only",
    "is_native_or_attribution",
]
