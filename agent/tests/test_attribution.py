"""Tests for napg.attribution — the ERC-8021 Builder Code suffix helper."""

from __future__ import annotations

import pytest

from napg.attribution import (
    ERC8021_MARKER,
    append_suffix,
    build_suffix,
    is_attribution_only,
    is_native_or_attribution,
)

# The worked example from the Base docs for the code "baseapp".
_BASEAPP_SUFFIX = "0x07626173656170700080218021802180218021802180218021"


def test_build_suffix_matches_the_base_docs_example():
    assert build_suffix("baseapp") == _BASEAPP_SUFFIX


def test_suffix_layout_len_code_schema_marker():
    suffix = bytes.fromhex(build_suffix("napg").removeprefix("0x"))
    assert suffix[0] == 4  # len("napg")
    assert suffix[1:5] == b"napg"
    assert suffix[5] == 0  # schema 0
    assert suffix[6:] == ERC8021_MARKER
    assert len(ERC8021_MARKER) == 16


def test_build_suffix_rejects_empty_code():
    with pytest.raises(ValueError, match="non-empty"):
        build_suffix("")


def test_build_suffix_rejects_non_ascii():
    with pytest.raises(ValueError, match="ASCII"):
        build_suffix("napg✨")


def test_build_suffix_rejects_overlong_code():
    with pytest.raises(ValueError, match="at most 255"):
        build_suffix("a" * 256)


def test_append_suffix_to_native_calldata():
    assert append_suffix("0x", "baseapp") == _BASEAPP_SUFFIX


def test_append_suffix_to_existing_calldata():
    base = "0xabcdef"
    out = append_suffix(base, "napg")
    assert out.startswith(base)
    assert out.endswith(build_suffix("napg").removeprefix("0x"))


def test_append_suffix_rejects_non_hex_base():
    with pytest.raises(ValueError, match="0x-hex"):
        append_suffix("deadbeef", "napg")


def test_is_attribution_only_true_for_exact_suffix():
    assert is_attribution_only(build_suffix("napg"), "napg") is True


def test_is_attribution_only_case_insensitive():
    assert is_attribution_only(build_suffix("napg").upper(), "napg") is True


def test_is_attribution_only_false_for_wrong_code():
    assert is_attribution_only(build_suffix("napg"), "baseapp") is False


def test_is_attribution_only_false_when_no_code_configured():
    assert is_attribution_only(build_suffix("napg"), None) is False


def test_is_attribution_only_false_for_calldata_with_prefix():
    # A contract call that merely *ends* with our suffix must not be accepted.
    sneaky = "0xdeadbeef" + build_suffix("napg").removeprefix("0x")
    assert is_attribution_only(sneaky, "napg") is False


def test_is_native_or_attribution():
    assert is_native_or_attribution("0x", None) is True
    assert is_native_or_attribution("0x", "napg") is True
    assert is_native_or_attribution(build_suffix("napg"), "napg") is True
    assert is_native_or_attribution(build_suffix("napg"), None) is False
    assert is_native_or_attribution("0xdeadbeef", "napg") is False
