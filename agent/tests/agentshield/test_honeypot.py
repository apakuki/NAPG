"""Tests for the AgentShield Honeypot Detection stage (Stage 4) and cache."""

from __future__ import annotations

from napg.agentshield.pipeline import TxIntent
from napg.agentshield.stages.honeypot import HoneypotCache, build_honeypot_stage

ADDR_AGENT = "0x" + "a" * 40
ADDR_SAFE = "0x" + "b" * 40
ADDR_TOKEN = "0x" + "c" * 40


def _intent(data: str = "0x") -> TxIntent:
    return TxIntent(
        action="migrate_to_safe",
        from_address=ADDR_AGENT,
        to_address=ADDR_SAFE,
        value_wei=1000,
        data=data,
    )


# ---- Stage 4 callable ----


def test_native_transfer_passes_trivially() -> None:
    stage = build_honeypot_stage()
    result = stage(_intent("0x"))
    assert result.passed is True
    assert result.stage == "honeypot"
    assert "no target token" in result.reason


def test_non_native_calldata_fails_closed_until_token_actions_land() -> None:
    stage = build_honeypot_stage()
    result = stage(_intent("0xa9059cbb000000"))
    assert result.passed is False
    assert "BUY-then-SELL" in result.reason


def test_stage_attaches_cache_size_to_native_pass() -> None:
    cache = HoneypotCache()
    cache.set(ADDR_TOKEN, "0xdeadbeef", is_safe=True)
    stage = build_honeypot_stage(cache=cache)
    result = stage(_intent("0x"))
    assert result.details["cache_size"] == 1


# ---- HoneypotCache contract ----


def test_cache_round_trips_lowercased() -> None:
    cache = HoneypotCache()
    cache.set("0xABCDEF" + "0" * 34, "0xCAFEBABE", is_safe=True)
    assert cache.get("0xabcdef" + "0" * 34, "0xcafebabe") is True
    assert cache.get("0xabcdef" + "0" * 34, "0xc0ffee") is None  # different hash


def test_cache_returns_none_for_unknown() -> None:
    cache = HoneypotCache()
    assert cache.get("0x" + "f" * 40, "0xabc") is None


def test_cache_evict_older_than_drops_stale_entries() -> None:
    """When the live codeHash changes, the stored verdict is no longer trustworthy."""
    cache = HoneypotCache()
    cache.set(ADDR_TOKEN, "0xold-hash", is_safe=True)
    cache.set("0x" + "d" * 40, "0xkept-hash", is_safe=False)
    dropped = cache.evict_older_than({ADDR_TOKEN: "0xnew-hash"})
    assert dropped == 1
    assert cache.get(ADDR_TOKEN, "0xold-hash") is None
    assert cache.get("0x" + "d" * 40, "0xkept-hash") is False


def test_cache_evict_no_op_when_hash_matches() -> None:
    cache = HoneypotCache()
    cache.set(ADDR_TOKEN, "0xsame-hash", is_safe=True)
    dropped = cache.evict_older_than({ADDR_TOKEN: "0xsame-hash"})
    assert dropped == 0
    assert cache.get(ADDR_TOKEN, "0xsame-hash") is True


def test_cache_len_reflects_entries() -> None:
    cache = HoneypotCache()
    assert len(cache) == 0
    cache.set("0x" + "a" * 40, "0x1", True)
    cache.set("0x" + "b" * 40, "0x2", False)
    assert len(cache) == 2
