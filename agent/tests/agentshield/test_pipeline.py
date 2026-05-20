"""Skeleton tests for the AgentShield `validate_or_die` pipeline."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from napg.agentshield import (
    StageResult,
    TxIntent,
    ValidationFailure,
    validate_or_die,
)
from napg.audit import AuditLog

SAMPLE_INTENT = TxIntent(
    action="migrate_to_safe",
    from_address="0x" + "a" * 40,
    to_address="0x" + "b" * 40,
    value_wei=1000,
    rationale="test",
    supporting_breaches=("rpc_latency_ms_max",),
)


def _ok(stage: str):
    def _fn(intent: TxIntent) -> StageResult:
        return StageResult(stage=stage, passed=True)

    return _fn


def _fail(stage: str, reason: str):
    def _fn(intent: TxIntent) -> StageResult:
        return StageResult(stage=stage, passed=False, reason=reason)

    return _fn


def test_pipeline_runs_all_stages_in_order_on_success() -> None:
    called: list[str] = []

    def _spy(stage: str):
        def _fn(intent: TxIntent) -> StageResult:
            called.append(stage)
            return StageResult(stage=stage, passed=True)

        return _fn

    result = validate_or_die(
        SAMPLE_INTENT,
        intent_judge=_spy("intent_judge"),
        policy=_spy("policy"),
        tenderly=_spy("tenderly"),
        honeypot=_spy("honeypot"),
        kill_switch=lambda: False,
    )

    assert called == ["intent_judge", "policy", "tenderly", "honeypot"]
    assert result.passed is True
    assert result.kill_switch_engaged is False
    assert tuple(s.stage for s in result.stages) == (
        "intent_judge",
        "policy",
        "tenderly",
        "honeypot",
    )


def test_failing_stage_short_circuits_subsequent_stages() -> None:
    called: list[str] = []

    def _spy(stage: str):
        def _fn(intent: TxIntent) -> StageResult:
            called.append(stage)
            return StageResult(stage=stage, passed=True)

        return _fn

    with pytest.raises(ValidationFailure) as excinfo:
        validate_or_die(
            SAMPLE_INTENT,
            intent_judge=_spy("intent_judge"),
            policy=_fail("policy", "destination denylisted"),
            tenderly=_spy("tenderly"),
            honeypot=_spy("honeypot"),
            kill_switch=lambda: False,
        )

    assert called == ["intent_judge"]
    failing = [s for s in excinfo.value.result.stages if not s.passed]
    assert len(failing) == 1
    assert failing[0].stage == "policy"
    assert "destination denylisted" in str(excinfo.value)


def test_kill_switch_blocks_before_any_stage_runs() -> None:
    called: list[str] = []

    def _spy(stage: str):
        def _fn(intent: TxIntent) -> StageResult:
            called.append(stage)
            return StageResult(stage=stage, passed=True)

        return _fn

    with pytest.raises(ValidationFailure) as excinfo:
        validate_or_die(
            SAMPLE_INTENT,
            intent_judge=_spy("intent_judge"),
            policy=_spy("policy"),
            tenderly=_spy("tenderly"),
            honeypot=_spy("honeypot"),
            kill_switch=lambda: True,
        )

    assert called == []
    assert excinfo.value.result.kill_switch_engaged is True
    assert excinfo.value.result.stages == ()
    assert "kill-switch" in str(excinfo.value)


def test_default_stages_raise_notimplemented(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production default is fail-closed: unimplemented stages refuse to validate."""
    monkeypatch.delenv("NAPG_KILL_SWITCH", raising=False)
    with pytest.raises(NotImplementedError) as excinfo:
        validate_or_die(SAMPLE_INTENT)
    assert "Intent Judge" in str(excinfo.value)


def test_env_kill_switch_engages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NAPG_KILL_SWITCH", "1")
    with pytest.raises(ValidationFailure) as excinfo:
        validate_or_die(
            SAMPLE_INTENT,
            intent_judge=_ok("intent_judge"),
            policy=_ok("policy"),
            tenderly=_ok("tenderly"),
            honeypot=_ok("honeypot"),
        )
    assert excinfo.value.result.kill_switch_engaged is True


def test_env_kill_switch_disengaged_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NAPG_KILL_SWITCH", raising=False)
    result = validate_or_die(
        SAMPLE_INTENT,
        intent_judge=_ok("intent_judge"),
        policy=_ok("policy"),
        tenderly=_ok("tenderly"),
        honeypot=_ok("honeypot"),
    )
    assert result.passed is True


def test_audit_row_lands_on_success(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NAPG_KILL_SWITCH", raising=False)
    db_path = tmp_path / "audit.db"
    with AuditLog(str(db_path), hmac_key="test-key") as log:
        validate_or_die(
            SAMPLE_INTENT,
            audit_log=log,
            intent_judge=_ok("intent_judge"),
            policy=_ok("policy"),
            tenderly=_ok("tenderly"),
            honeypot=_ok("honeypot"),
        )
        rows = list(log.iter_rows())
    assert len(rows) == 1
    assert rows[0].kind == "validation"
    assert rows[0].payload["passed"] is True
    assert rows[0].payload["intent"]["action"] == "migrate_to_safe"


def test_audit_row_lands_on_failure(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NAPG_KILL_SWITCH", raising=False)
    db_path = tmp_path / "audit.db"
    with AuditLog(str(db_path), hmac_key="test-key") as log:
        with pytest.raises(ValidationFailure):
            validate_or_die(
                SAMPLE_INTENT,
                audit_log=log,
                intent_judge=_ok("intent_judge"),
                policy=_fail("policy", "denylisted destination"),
                tenderly=_ok("tenderly"),
                honeypot=_ok("honeypot"),
            )
        rows = list(log.iter_rows())
    assert len(rows) == 1
    assert rows[0].kind == "validation"
    assert rows[0].payload["passed"] is False
    failing = [s for s in rows[0].payload["stages"] if not s["passed"]]
    assert len(failing) == 1
    assert failing[0]["stage"] == "policy"


def test_audit_row_lands_when_kill_switch_engaged(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NAPG_KILL_SWITCH", "1")
    db_path = tmp_path / "audit.db"
    with AuditLog(str(db_path), hmac_key="test-key") as log:
        with pytest.raises(ValidationFailure):
            validate_or_die(
                SAMPLE_INTENT,
                audit_log=log,
                intent_judge=_ok("intent_judge"),
                policy=_ok("policy"),
                tenderly=_ok("tenderly"),
                honeypot=_ok("honeypot"),
            )
        rows = list(log.iter_rows())
    assert len(rows) == 1
    assert rows[0].kind == "validation"
    assert rows[0].payload["kill_switch_engaged"] is True
    assert rows[0].payload["stages"] == []


def test_intent_is_immutable_after_construction() -> None:
    intent = TxIntent(
        action="migrate_to_safe",
        from_address="0x" + "a" * 40,
        to_address="0x" + "b" * 40,
        value_wei=1,
    )
    with pytest.raises(ValidationError):
        intent.value_wei = 2  # type: ignore[misc]


def test_intent_rejects_short_address() -> None:
    with pytest.raises(ValidationError):
        TxIntent(
            action="migrate_to_safe",
            from_address="0xshort",
            to_address="0x" + "b" * 40,
            value_wei=1,
        )
