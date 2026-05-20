"""Tests for the AgentShield Intent Judge (Stage 1).

The Anthropic SDK is mocked; no network calls.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from napg.agentshield.pipeline import TxIntent
from napg.agentshield.stages.intent_judge import build_intent_judge_stage

ADDR_AGENT = "0x" + "a" * 40
ADDR_SAFE = "0x" + "b" * 40


def _intent(rationale: str = "Reorg breach drove migrate decision.") -> TxIntent:
    return TxIntent(
        action="migrate_to_safe",
        from_address=ADDR_AGENT,
        to_address=ADDR_SAFE,
        value_wei=1_000_000_000_000_000,  # 0.001 ETH
        rationale=rationale,
        supporting_breaches=("reorg_is_breach",),
    )


def _fake_response(verdict: str, reason: str = "ok") -> SimpleNamespace:
    block = SimpleNamespace(
        type="tool_use",
        name="submit_verdict",
        input={"verdict": verdict, "reason": reason},
    )
    return SimpleNamespace(
        content=[block],
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
        model="claude-opus-4-7",
    )


def _client_returning(response: SimpleNamespace) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = response
    return client


def test_agree_passes_stage() -> None:
    client = _client_returning(_fake_response("agree", "rationale matches action"))
    stage = build_intent_judge_stage(api_key="sk-test", client=client)
    result = stage(_intent())
    assert result.passed is True
    assert result.stage == "intent_judge"
    assert result.details["verdict"] == "agree"
    assert "rationale matches action" in result.reason


def test_disagree_fails_stage() -> None:
    client = _client_returning(
        _fake_response("disagree", "rationale describes green state but action is migrate")
    )
    stage = build_intent_judge_stage(api_key="sk-test", client=client)
    result = stage(_intent(rationale="all green"))
    assert result.passed is False
    assert "judge disagree" in result.reason
    assert result.details["verdict"] == "disagree"


def test_abstain_fails_stage() -> None:
    """Abstain is not consent — fail closed on uncertainty."""
    client = _client_returning(_fake_response("abstain", "ambiguous input"))
    stage = build_intent_judge_stage(api_key="sk-test", client=client)
    result = stage(_intent())
    assert result.passed is False
    assert "judge abstain" in result.reason


def test_requires_api_key() -> None:
    with pytest.raises(ValueError, match="API key"):
        build_intent_judge_stage(api_key="")


def test_missing_tool_use_raises_runtime_error() -> None:
    """A response without the submit_verdict block is treated as malformed."""
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="just chatting")],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        model="claude-opus-4-7",
    )
    client = _client_returning(response)
    stage = build_intent_judge_stage(api_key="sk-test", client=client)
    with pytest.raises(RuntimeError, match="submit_verdict"):
        stage(_intent())


def test_call_includes_cached_system_prompt() -> None:
    client = _client_returning(_fake_response("agree"))
    stage = build_intent_judge_stage(api_key="sk-test", client=client)
    stage(_intent())
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["tools"][0]["name"] == "submit_verdict"
    assert kwargs["tool_choice"]["name"] == "submit_verdict"
    system = kwargs["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_user_message_carries_intent_fields() -> None:
    client = _client_returning(_fake_response("agree"))
    stage = build_intent_judge_stage(api_key="sk-test", client=client)
    stage(_intent(rationale="some specific rationale"))
    kwargs = client.messages.create.call_args.kwargs
    user_content = kwargs["messages"][0]["content"]
    assert "migrate_to_safe" in user_content
    assert "some specific rationale" in user_content
    assert "reorg_is_breach" in user_content
    assert ADDR_SAFE in user_content
