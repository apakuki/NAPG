"""Tests for napg.redact — single boundary for stripping sensitive material."""

from __future__ import annotations

from napg.redact import redact_url


def test_strips_path_with_api_key():
    raw = "https://base-sepolia.g.alchemy.com/v2/secret-key-abcdef"
    assert redact_url(raw) == "https://base-sepolia.g.alchemy.com/<redacted>"


def test_strips_query_string():
    raw = "https://rpc.example.com/?api_key=secret"
    assert redact_url(raw) == "https://rpc.example.com/<redacted>"


def test_preserves_bare_host():
    assert redact_url("https://rpc.example.com") == "https://rpc.example.com"


def test_treats_root_slash_as_no_path():
    assert redact_url("https://rpc.example.com/") == "https://rpc.example.com"


def test_strips_userinfo_via_hostname_only():
    raw = "https://user:pass@rpc.example.com/v2/key"
    redacted = redact_url(raw)
    assert "user" not in redacted
    assert "pass" not in redacted
    assert redacted == "https://rpc.example.com/<redacted>"


def test_preserves_non_default_port():
    raw = "https://rpc.example.com:8443/v2/key"
    assert redact_url(raw) == "https://rpc.example.com:8443/<redacted>"
