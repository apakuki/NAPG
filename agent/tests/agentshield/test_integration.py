"""Phase 2 integration tests for `validate_or_die`.

These exercise the full pipeline (kill-switch -> Intent Judge -> Policy
-> Tenderly -> Honeypot) end to end with stubbed external services
where needed. They are the negative-path counterpart to the per-stage
unit tests: confirm that a real-shaped failure on each stage really
does block the tx and lands the correct audit row.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from napg.agentshield.pipeline import (
    StageResult,
    TxIntent,
    ValidationFailure,
    validate_or_die,
)
from napg.agentshield.policy import Denylist, PolicyConfig
from napg.agentshield.stages.honeypot import build_honeypot_stage
from napg.agentshield.stages.policy import build_policy_stage
from napg.audit import AuditLog

ADDR_AGENT = "0x" + "a" * 40
ADDR_SAFE = "0x" + "b" * 40
ADDR_BAD = "0x" + "c" * 40

DEFAULT_POLICY = PolicyConfig(
    max_value_wei_per_tx=1_000_000_000_000_000,
    daily_spend_cap_wei=5_000_000_000_000_000,
)
DENYLIST_WITH_BAD = Denylist(addresses=(ADDR_BAD,))


def _passing(stage: str):
    def _fn(intent: TxIntent) -> StageResult:
        return StageResult(stage=stage, passed=True)

    return _fn


def _intent_to(addr: str, value_wei: int = 1) -> TxIntent:
    return TxIntent(
        action="migrate_to_safe",
        from_address=ADDR_AGENT,
        to_address=addr,
        value_wei=value_wei,
        rationale="reorg detected",
        supporting_breaches=("reorg_is_breach",),
    )


def test_denylisted_destination_blocks_at_policy_stage_and_audits(tmp_path: Path) -> None:
    """A tx to a denylisted destination must fail Stage 2 with a `validation`
    row carrying the denylist reason — and no `action` row."""
    db_path = tmp_path / "audit.db"
    with AuditLog(str(db_path), hmac_key="test-key") as log:
        policy_stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=DENYLIST_WITH_BAD)
        honeypot_stage = build_honeypot_stage()
        with pytest.raises(ValidationFailure) as excinfo:
            validate_or_die(
                _intent_to(ADDR_BAD),
                audit_log=log,
                intent_judge=_passing("intent_judge"),
                policy=policy_stage,
                tenderly=_passing("tenderly"),
                honeypot=honeypot_stage,
                kill_switch=lambda: False,
            )
        rows = list(log.iter_rows())

    failing = [s for s in excinfo.value.result.stages if not s.passed]
    assert len(failing) == 1
    assert failing[0].stage == "policy"
    assert "denylist" in failing[0].reason
    assert len(rows) == 1
    assert rows[0].kind == "validation"
    assert rows[0].payload["passed"] is False
    # No action row landed.
    assert all(r.kind != "action" for r in rows)


def test_per_tx_cap_exceeded_blocks_at_policy_stage(tmp_path: Path) -> None:
    """A value above per-tx cap fails Stage 2 even with denylist clean."""
    db_path = tmp_path / "audit.db"
    with AuditLog(str(db_path), hmac_key="test-key") as log:
        policy_stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=Denylist())
        with pytest.raises(ValidationFailure) as excinfo:
            validate_or_die(
                _intent_to(ADDR_SAFE, value_wei=DEFAULT_POLICY.max_value_wei_per_tx + 1),
                audit_log=log,
                intent_judge=_passing("intent_judge"),
                policy=policy_stage,
                tenderly=_passing("tenderly"),
                honeypot=build_honeypot_stage(),
                kill_switch=lambda: False,
            )
        rows = list(log.iter_rows())

    failing = [s for s in excinfo.value.result.stages if not s.passed]
    assert failing[0].stage == "policy"
    assert "per-tx cap" in failing[0].reason
    assert len(rows) == 1


def test_replay_same_inputs_yields_same_decision() -> None:
    """Deterministic stages: running the same intent through the same stage
    instances twice must yield identical pass/fail/reason outputs.

    The LLM-based Intent Judge is stubbed deterministically here — the
    non-determinism that exists in production is the LLM call itself, which
    AgentShield gates on a strict three-value verdict that fail-closes any
    output outside the enum.
    """
    intent = _intent_to(ADDR_SAFE, value_wei=1)
    policy_stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=DENYLIST_WITH_BAD)
    honeypot_stage = build_honeypot_stage()
    kwargs = {
        "intent_judge": _passing("intent_judge"),
        "policy": policy_stage,
        "tenderly": _passing("tenderly"),
        "honeypot": honeypot_stage,
        "kill_switch": lambda: False,
    }
    first = validate_or_die(intent, **kwargs)
    second = validate_or_die(intent, **kwargs)
    assert first.passed == second.passed
    assert tuple((s.stage, s.passed, s.reason) for s in first.stages) == tuple(
        (s.stage, s.passed, s.reason) for s in second.stages
    )


def test_negative_test_removing_a_stage_collapses_to_default_fail() -> None:
    """If a caller forgets to supply a stage, the production default
    (`NotImplementedError`) fail-closes the pipeline — confirming the
    pipeline cannot 'silently skip' a stage."""
    with pytest.raises(NotImplementedError) as excinfo:
        validate_or_die(
            _intent_to(ADDR_SAFE),
            # No policy stage supplied.
            intent_judge=_passing("intent_judge"),
            tenderly=_passing("tenderly"),
            honeypot=build_honeypot_stage(),
            kill_switch=lambda: False,
        )
    assert "Policy" in str(excinfo.value)
