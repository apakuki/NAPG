"""The `validate_or_die` pipeline — one function, four stages, fail-closed.

Order of operations:

    kill-switch -> Stage 1 Intent Judge -> Stage 2 Policy
                -> Stage 3 Tenderly -> Stage 4 Honeypot

First failure short-circuits; subsequent stages do not run. A
`ValidationResult` always lands in the audit log when an `AuditLog` is
provided — pass or fail, kill-switched or not — so an investigator can
reconstruct the full attempted history later.

The four stage callables are injectable so each Phase 2 substep can land
its stage without changing this module. Production defaults raise
`NotImplementedError`, which keeps the pipeline fail-closed until every
stage is live.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from napg.audit import AuditLog

_KILL_SWITCH_ENV = "NAPG_KILL_SWITCH"


class TxIntent(BaseModel):
    """The shape every action declares before signing.

    Frozen so an intent that has already been validated cannot be mutated
    between the validation call and the wallet call. `from_address` and
    `to_address` are checked-checksum length only here; format/allowlist
    validation belongs to Stage 2 (Policy).
    """

    model_config = ConfigDict(frozen=True)

    action: str = Field(min_length=1)
    from_address: str = Field(min_length=42, max_length=42)
    to_address: str = Field(min_length=42, max_length=42)
    value_wei: int = Field(ge=0)
    data: str = Field(default="0x", description="calldata hex; '0x' for native transfer")
    rationale: str = Field(default="", description="reasoner-stated rationale for this tx")
    supporting_breaches: tuple[str, ...] = ()
    # Group E swap economics. Present only on swap intents (action == "swap");
    # None for native transfers. AgentShield's Stage 2 slippage floor requires
    # min_out_wei + quoted_out_wei on any swap and fails closed without them.
    min_out_wei: int | None = Field(default=None, ge=0)
    quoted_out_wei: int | None = Field(default=None, ge=0)
    token_in: str | None = None
    token_out: str | None = None

    @property
    def is_swap(self) -> bool:
        """A swap intent declares `action == "swap"`. The future swap action sets
        this explicitly; native transfers (migrate_to_safe) never do."""
        return self.action == "swap"


class StageResult(BaseModel):
    """One stage's outcome. `passed=False` short-circuits the pipeline."""

    model_config = ConfigDict(frozen=True)

    stage: str
    passed: bool
    reason: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    """Aggregated outcome of one `validate_or_die` call."""

    model_config = ConfigDict(frozen=True)

    intent: TxIntent
    stages: tuple[StageResult, ...]
    passed: bool
    kill_switch_engaged: bool = False


class ValidationFailure(RuntimeError):
    """Raised when any stage fails or the kill-switch is engaged.

    Carries the full `ValidationResult` so the caller can render an
    explanation; the audit row contains the same payload structurally.
    """

    def __init__(self, result: ValidationResult) -> None:
        self.result = result
        if result.kill_switch_engaged:
            super().__init__("AgentShield: kill-switch engaged; signing blocked")
            return
        failing = [s for s in result.stages if not s.passed]
        if failing:
            reasons = "; ".join(f"{s.stage}: {s.reason}" for s in failing)
            super().__init__(f"AgentShield blocked tx: {reasons}")
        else:
            super().__init__("AgentShield blocked tx (no specific reason recorded)")


StageFn = Callable[[TxIntent], StageResult]
KillSwitchFn = Callable[[], bool]


def _env_kill_switch() -> bool:
    """Phase 2 kill-switch: `NAPG_KILL_SWITCH=1` blocks signing.

    Phase 5 replaces this with a signed-message variant; the wrapping API
    stays the same so callers and tests do not change.
    """
    return os.environ.get(_KILL_SWITCH_ENV) == "1"


def _not_yet_implemented(stage_name: str) -> StageFn:
    """Build a fail-closed default stage callable for `stage_name`.

    Each Phase 2 substep that lands a real stage swaps in its own callable
    at the call site (or eventually as the module-level default). Until
    then the default refuses to validate and the pipeline fails closed.
    """

    def _stage(intent: TxIntent) -> StageResult:
        raise NotImplementedError(
            f"AgentShield {stage_name} stage is not yet implemented; "
            "callers must inject a stage callable until the live one lands."
        )

    return _stage


def validate_or_die(
    intent: TxIntent,
    *,
    audit_log: AuditLog | None = None,
    intent_judge: StageFn | None = None,
    policy: StageFn | None = None,
    tenderly: StageFn | None = None,
    honeypot: StageFn | None = None,
    kill_switch: KillSwitchFn | None = None,
    now: float | None = None,
) -> ValidationResult:
    """Run the 4-stage validation pipeline. Fail-closed."""
    kill = kill_switch if kill_switch is not None else _env_kill_switch
    intent_judge_fn = intent_judge or _not_yet_implemented("Intent Judge")
    policy_fn = policy or _not_yet_implemented("Policy")
    tenderly_fn = tenderly or _not_yet_implemented("Tenderly")
    honeypot_fn = honeypot or _not_yet_implemented("Honeypot")

    if kill():
        result = ValidationResult(
            intent=intent,
            stages=(),
            passed=False,
            kill_switch_engaged=True,
        )
        _emit_audit(audit_log, result, at=now)
        raise ValidationFailure(result)

    stages: list[StageResult] = []
    for stage_fn in (intent_judge_fn, policy_fn, tenderly_fn, honeypot_fn):
        stage_result = stage_fn(intent)
        stages.append(stage_result)
        if not stage_result.passed:
            failed = ValidationResult(intent=intent, stages=tuple(stages), passed=False)
            _emit_audit(audit_log, failed, at=now)
            raise ValidationFailure(failed)

    result = ValidationResult(intent=intent, stages=tuple(stages), passed=True)
    _emit_audit(audit_log, result, at=now)
    return result


def _emit_audit(audit_log: AuditLog | None, result: ValidationResult, *, at: float | None) -> None:
    if audit_log is None:
        return
    payload = json.loads(result.model_dump_json())
    audit_log.record("validation", payload, at=at)


__all__ = [
    "StageResult",
    "TxIntent",
    "ValidationFailure",
    "ValidationResult",
    "validate_or_die",
]
