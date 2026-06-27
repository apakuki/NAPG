"""Production-wiring helpers for AgentShield.

Composes the four live stages from `Settings` and returns a single
callable the action layer can use as its validator:

    validator: Callable[[TxIntent], ValidationResult]

The callable raises `ValidationFailure` on any stage failure or
engaged kill-switch — `napg.actions.migrate_to_safe` simply calls it
and lets the exception propagate up to the orchestrator / CLI for
audit + return.

Tests use stub validators (see `tests/agentshield/test_pipeline.py`);
the production code goes through this helper so the live wire-up
lives in exactly one place.
"""

from __future__ import annotations

from collections.abc import Callable

from napg.agentshield.pipeline import (
    TxIntent,
    ValidationResult,
    validate_or_die,
)
from napg.agentshield.policy import (
    default_denylist_path,
    default_policy_path,
    default_public_key_path,
    load_denylist,
    load_policy,
)
from napg.agentshield.stages.honeypot import build_honeypot_stage
from napg.agentshield.stages.intent_judge import build_intent_judge_stage
from napg.agentshield.stages.policy import build_policy_stage
from napg.agentshield.stages.tenderly import build_tenderly_stage
from napg.audit import AuditLog
from napg.config import Settings

_NETWORK_TO_CHAIN_ID = {"base-sepolia": 84532, "base-mainnet": 8453}


def build_production_validator(
    settings: Settings,
    *,
    audit_log: AuditLog | None = None,
) -> Callable[[TxIntent], ValidationResult]:
    """Compose the four live stages and return the validator callable.

    Raises `RuntimeError` early if any required Setting is missing — better
    to fail at boot than to fail on the first signing attempt.
    """
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY required for AgentShield Intent Judge")
    if not (
        settings.tenderly_account_slug
        and settings.tenderly_project_slug
        and settings.tenderly_access_key
    ):
        raise RuntimeError("Tenderly credentials required for AgentShield Stage 3")

    chain_id = _NETWORK_TO_CHAIN_ID.get(settings.network)
    if chain_id is None:
        raise RuntimeError(f"unsupported network for AgentShield: {settings.network!r}")

    public_key_path = default_public_key_path()
    policy_config = load_policy(default_policy_path(), public_key_path)
    denylist = load_denylist(default_denylist_path(), public_key_path)

    intent_judge = build_intent_judge_stage(api_key=settings.anthropic_api_key)
    policy_stage = build_policy_stage(
        policy=policy_config,
        denylist=denylist,
        audit_log=audit_log,
        builder_code=settings.builder_code,
    )
    tenderly_stage = build_tenderly_stage(
        account_slug=settings.tenderly_account_slug,
        project_slug=settings.tenderly_project_slug,
        access_key=settings.tenderly_access_key,
        network_id=chain_id,
    )
    honeypot_stage = build_honeypot_stage(builder_code=settings.builder_code)

    def _validate(intent: TxIntent) -> ValidationResult:
        return validate_or_die(
            intent,
            audit_log=audit_log,
            intent_judge=intent_judge,
            policy=policy_stage,
            tenderly=tenderly_stage,
            honeypot=honeypot_stage,
        )

    return _validate


__all__ = ["build_production_validator"]
