"""Unit tests for napg.monitor.rpc — covers HTTPS guard, latency, reorg, schema."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from napg.monitor.rpc import BlockSnapshot, RpcHeartbeat


def _block(number: int, hash_hex: str, parent_hex: str, ts: int = 1_700_000_000) -> dict[str, Any]:
    return {
        "number": number,
        "hash": bytes.fromhex(hash_hex[2:]),
        "parentHash": bytes.fromhex(parent_hex[2:]),
        "timestamp": ts,
    }


HASH_A = "0x" + "aa" * 32
HASH_B = "0x" + "bb" * 32
HASH_C = "0x" + "cc" * 32
HASH_D = "0x" + "dd" * 32


def _make_web3(chain_id: int, blocks: list[dict[str, Any]]) -> MagicMock:
    """Mock Web3 whose `eth.get_block("latest")` walks through `blocks` in order."""
    web3 = MagicMock()
    web3.eth.chain_id = chain_id
    iterator = iter(blocks)
    web3.eth.get_block.side_effect = lambda _identifier: next(iterator)
    return web3


def test_https_required():
    with pytest.raises(ValueError, match="https"):
        RpcHeartbeat("http://insecure.example/rpc")


def test_https_required_for_other_schemes():
    with pytest.raises(ValueError, match="https"):
        RpcHeartbeat("ws://example/rpc")


def test_tick_reports_latency_block_and_chain():
    web3 = _make_web3(84532, [_block(100, HASH_B, HASH_A)])
    heart = RpcHeartbeat("https://sepolia.example/rpc", web3=web3)

    result = heart.tick()

    assert result.chain_id == 84532
    assert result.rpc_url == "https://sepolia.example/<redacted>"
    assert "rpc" not in result.rpc_url  # path stripped at construction
    assert result.block.number == 100
    assert result.block.hash == HASH_B
    assert result.block.parent_hash == HASH_A
    assert result.latency_ms >= 0
    assert result.reorg_detected is False
    assert result.observed_at > 0


def test_first_tick_has_no_reorg_signal():
    web3 = _make_web3(84532, [_block(50, HASH_A, HASH_B)])
    heart = RpcHeartbeat("https://sepolia.example/rpc", web3=web3)

    result = heart.tick()

    assert result.reorg_detected is False


def test_chained_blocks_do_not_flag_reorg():
    web3 = _make_web3(
        84532,
        [
            _block(100, HASH_A, HASH_D),
            _block(101, HASH_B, HASH_A),
            _block(102, HASH_C, HASH_B),
        ],
    )
    heart = RpcHeartbeat("https://sepolia.example/rpc", web3=web3)

    heart.tick()
    heart.tick()
    third = heart.tick()

    assert third.reorg_detected is False


def test_parent_hash_mismatch_flags_reorg():
    web3 = _make_web3(
        84532,
        [
            _block(100, HASH_A, HASH_D),
            _block(101, HASH_C, HASH_B),  # parent should be HASH_A; chain forked
        ],
    )
    heart = RpcHeartbeat("https://sepolia.example/rpc", web3=web3)

    heart.tick()
    second = heart.tick()

    assert second.reorg_detected is True


def test_history_replaces_block_when_same_height_returns():
    web3 = _make_web3(
        84532,
        [
            _block(100, HASH_A, HASH_D),
            _block(100, HASH_B, HASH_D),  # same height, different hash (reorg replay)
            _block(101, HASH_C, HASH_B),  # chains off the replacement, not the original
        ],
    )
    heart = RpcHeartbeat("https://sepolia.example/rpc", web3=web3)

    heart.tick()
    heart.tick()
    third = heart.tick()

    assert third.reorg_detected is False
    heights = [snap.number for snap in heart.history]
    assert heights.count(100) == 1


def test_block_snapshot_rejects_malformed_hash():
    with pytest.raises(ValidationError):
        BlockSnapshot(number=1, hash="0xdeadbeef", parent_hash=HASH_A, timestamp=1)


def test_block_snapshot_rejects_negative_number():
    with pytest.raises(ValidationError):
        BlockSnapshot(number=-1, hash=HASH_A, parent_hash=HASH_B, timestamp=1)


def test_block_snapshot_rejects_unsupported_hash_type():
    with pytest.raises(ValidationError):
        BlockSnapshot(number=1, hash=12345, parent_hash=HASH_A, timestamp=1)


def test_block_snapshot_accepts_str_without_prefix():
    snap = BlockSnapshot(number=1, hash="aa" * 32, parent_hash=HASH_B, timestamp=1)
    assert snap.hash == HASH_A


def test_history_size_caps_retained_blocks():
    blocks = [_block(n, f"0x{n:064x}", f"0x{n - 1:064x}") for n in range(1, 6)]
    web3 = _make_web3(84532, blocks)
    heart = RpcHeartbeat("https://sepolia.example/rpc", web3=web3, history_size=3)

    for _ in blocks:
        heart.tick()

    assert len(heart.history) == 3
    assert heart.history[-1].number == 5
