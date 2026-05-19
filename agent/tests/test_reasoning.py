"""Unit tests for napg.reasoning — tool-use parsing, cache metadata, audit hook.

The Anthropic SDK is mocked: we never make a network call from the test suite.
The mock client exposes the same `messages.create` surface and returns a
response shaped like a real one (tool_use content block + usage stats).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from napg.audit import AuditLog, verify
from napg.monitor.rpc import BlockSnapshot, HeartbeatResult
from napg.policy.breaches import Breach
from napg.reasoning import (
    DECISION_TOOL,
    SYSTEM_PROMPT,
    CacheMetadata,
    Decision,
    Reasoner,
    ReasoningInputs,
)

HASH_A = "0x" + "aa" * 32
HASH_B = "0x" + "bb" * 32

HMAC_KEY = "test-hmac-key-do-not-use-in-prod"


def _fake_response(
    *,
    intent: str = "migrate_to_safe",
    rationale: str = "Reorg breach + 100 bps peg breach observed; chain integrity floor violated.",
    confidence: float = 0.92,
    supporting_breaches: tuple[str, ...] = ("reorg_is_breach", "peg_deviation_bps_max"),
    model: str = "claude-opus-4-7",
    input_tokens: int = 500,
    output_tokens: int = 64,
    cache_creation: int = 0,
    cache_read: int = 1500,
) -> SimpleNamespace:
    tool_block = SimpleNamespace(
        type="tool_use",
        name="submit_decision",
        input={
            "intent": intent,
            "rationale": rationale,
            "confidence": confidence,
            "supporting_breaches": list(supporting_breaches),
        },
    )
    usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation,
        cache_read_input_tokens=cache_read,
    )
    return SimpleNamespace(content=[tool_block], usage=usage, model=model)


def _build_mock_client(response: SimpleNamespace) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = response
    return client


def _heartbeat(latency_ms: float = 100.0, reorg_detected: bool = False) -> HeartbeatResult:
    block = BlockSnapshot(number=10, hash=HASH_A, parent_hash=HASH_B, timestamp=1_716_000_000)
    return HeartbeatResult(
        rpc_url="https://example/<redacted>",
        chain_id=84532,
        latency_ms=latency_ms,
        block=block,
        reorg_detected=reorg_detected,
        observed_at=1_716_000_000.5,
    )


def _breach(rule: str = "reorg_is_breach") -> Breach:
    return Breach(
        rule=rule,
        source="heartbeat",
        threshold=False,
        actual=True,
        message="Reorg detected",
        detected_at=1_716_000_010.0,
    )


def test_requires_api_key() -> None:
    with pytest.raises(ValueError, match="API key"):
        Reasoner(api_key="")


def test_decide_returns_typed_decision() -> None:
    client = _build_mock_client(_fake_response())
    reasoner = Reasoner(api_key="sk-test", client=client)

    decision = reasoner.decide(
        ReasoningInputs(heartbeat=_heartbeat(reorg_detected=True), breaches=(_breach(),))
    )

    assert isinstance(decision, Decision)
    assert decision.intent == "migrate_to_safe"
    assert decision.supporting_breaches == ("reorg_is_breach", "peg_deviation_bps_max")
    assert decision.confidence == pytest.approx(0.92)
    assert decision.model == "claude-opus-4-7"


def test_cache_metadata_captured_from_usage() -> None:
    client = _build_mock_client(_fake_response(cache_creation=2000, cache_read=0))
    reasoner = Reasoner(api_key="sk-test", client=client)

    decision = reasoner.decide(ReasoningInputs(heartbeat=_heartbeat()))

    assert decision.cache_metadata == CacheMetadata(
        input_tokens=500,
        output_tokens=64,
        cache_creation_input_tokens=2000,
        cache_read_input_tokens=0,
    )


def test_cache_metadata_defaults_to_zero_when_fields_missing() -> None:
    """Older SDKs / odd responses may omit cache_* attributes; tolerate them."""
    response = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                name="submit_decision",
                input={
                    "intent": "hold",
                    "rationale": "no breaches",
                    "confidence": 0.99,
                    "supporting_breaches": [],
                },
            )
        ],
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
        model="claude-opus-4-7",
    )
    reasoner = Reasoner(api_key="sk-test", client=_build_mock_client(response))

    decision = reasoner.decide(ReasoningInputs(heartbeat=_heartbeat()))
    assert decision.cache_metadata.cache_creation_input_tokens == 0
    assert decision.cache_metadata.cache_read_input_tokens == 0


def test_messages_create_called_with_cached_system_block_and_tool_choice() -> None:
    client = _build_mock_client(_fake_response())
    reasoner = Reasoner(api_key="sk-test", client=client)

    reasoner.decide(ReasoningInputs(heartbeat=_heartbeat()))

    _, kwargs = client.messages.create.call_args
    system = kwargs["system"]
    assert isinstance(system, list)
    assert system[0]["text"] == SYSTEM_PROMPT
    assert system[0]["cache_control"] == {"type": "ephemeral"}

    assert kwargs["tools"] == [DECISION_TOOL]
    assert kwargs["tool_choice"] == {"type": "tool", "name": "submit_decision"}

    user_msg = kwargs["messages"][0]
    assert user_msg["role"] == "user"
    assert "submit_decision" in user_msg["content"]


def test_missing_tool_use_block_raises() -> None:
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="I refuse to call the tool.")],
        usage=SimpleNamespace(input_tokens=10, output_tokens=10),
        model="claude-opus-4-7",
    )
    reasoner = Reasoner(api_key="sk-test", client=_build_mock_client(response))

    with pytest.raises(RuntimeError, match="submit_decision"):
        reasoner.decide(ReasoningInputs(heartbeat=_heartbeat()))


def test_decide_writes_decision_row_to_audit_log(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    client = _build_mock_client(_fake_response(intent="hold", supporting_breaches=()))

    with AuditLog(db, hmac_key=HMAC_KEY) as log:
        reasoner = Reasoner(api_key="sk-test", client=client, audit_log=log)
        decision = reasoner.decide(ReasoningInputs(heartbeat=_heartbeat()))
        rows = list(log.iter_rows())

    assert len(rows) == 1
    row = rows[0]
    assert row.kind == "decision"
    assert row.payload["intent"] == "hold"
    assert row.payload["model"] == "claude-opus-4-7"
    assert row.payload["cache_metadata"]["cache_read_input_tokens"] == 1500
    assert decision.intent == "hold"


def test_audit_row_never_contains_the_api_key(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    secret_key = "sk-ant-do-not-leak-this-fake-key-please"
    client = _build_mock_client(_fake_response())

    with AuditLog(db, hmac_key=HMAC_KEY) as log:
        reasoner = Reasoner(api_key=secret_key, client=client, audit_log=log)
        reasoner.decide(ReasoningInputs(heartbeat=_heartbeat()))

    blob = db.read_bytes()
    assert secret_key.encode("utf-8") not in blob


def test_audit_row_passes_hmac_verification(tmp_path: Path) -> None:
    """Decision rows must satisfy the same HMAC contract as breach rows."""
    db = tmp_path / "audit.db"
    client = _build_mock_client(_fake_response())

    with AuditLog(db, hmac_key=HMAC_KEY) as log:
        reasoner = Reasoner(api_key="sk-test", client=client, audit_log=log)
        reasoner.decide(ReasoningInputs(heartbeat=_heartbeat()))

    result = verify(db, HMAC_KEY)
    assert result.ok
    assert result.total_rows == 1


def test_user_message_embeds_state_json() -> None:
    client = _build_mock_client(_fake_response())
    reasoner = Reasoner(api_key="sk-test", client=client)

    reasoner.decide(
        ReasoningInputs(
            heartbeat=_heartbeat(latency_ms=1234.5),
            breaches=(_breach("rpc_latency_ms_max"),),
        )
    )

    user_msg = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert '"latency_ms": 1234.5' in user_msg
    assert '"rule": "rpc_latency_ms_max"' in user_msg
