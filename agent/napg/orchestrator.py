"""One Phase 1 decision cycle, end to end.

Probes (heartbeat / Aerodrome / Morpho) are the inputs. The cycle evaluates
breaches against the configured thresholds, asks the reasoner what to do,
and dispatches the chosen action — `migrate_to_safe` is the only action in
Phase 1; `hold` and `pause_for_investigation` are no-ops at the dispatch
layer (the latter is still informative in the audit log).

The audit chain produced per cycle is:

    [scenario?] -> [breach...] -> [decision] -> [action?]

`scenario` is written by callers running a simulation (see `napg.scenarios`)
so a reader can tell a synthetic cycle apart from a live one without
inspecting payloads. `breach` rows only land when the evaluator returns
non-empty. `action` only lands when the reasoner picks `migrate_to_safe`.

The orchestrator is deliberately probe-agnostic: it takes already-collected
probe outputs rather than fetching them itself. That makes the simulation
path trivial (synthesise a `HeartbeatResult`, hand it in, run the cycle)
and keeps the I/O surface for live runs in the CLI rather than smeared
through library code.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from napg.actions import ActionRecord, migrate_to_safe
from napg.audit import AuditLog
from napg.monitor.aerodrome import LiquidityProbe
from napg.monitor.morpho import MorphoPoll
from napg.monitor.rpc import HeartbeatResult
from napg.policy.breaches import Breach, BreachThresholds, evaluate
from napg.reasoning import Decision, Reasoner, ReasoningInputs


class CycleReport(BaseModel):
    """What one `run_cycle()` did: breaches it saw, decision it took, action it dispatched."""

    model_config = ConfigDict(frozen=True)

    breaches: tuple[Breach, ...]
    decision: Decision
    action: ActionRecord | None = None


def run_cycle(
    *,
    reasoner: Reasoner,
    audit_log: AuditLog,
    thresholds: BreachThresholds,
    heartbeat: HeartbeatResult | None = None,
    liquidity: LiquidityProbe | None = None,
    morpho: MorphoPoll | None = None,
    wallet: object | None = None,
    safe_address: str | None = None,
    value_wei: int = 0,
    dry_run: bool = True,
    now: float | None = None,
) -> CycleReport:
    """Run one decision cycle and return a report of what happened.

    `wallet` is typed `object` here because the only contract the orchestrator
    needs is the one `migrate_to_safe` already enforces via its own Protocol.
    Re-stating it here would just create duplicate import surface.
    """
    breaches = evaluate(
        thresholds,
        heartbeat=heartbeat,
        liquidity=liquidity,
        morpho=morpho,
        now=now,
    )
    if breaches:
        audit_log.record_breaches(breaches, at=now)

    decision = reasoner.decide(
        ReasoningInputs(
            heartbeat=heartbeat,
            liquidity=liquidity,
            morpho=morpho,
            breaches=breaches,
        )
    )

    action: ActionRecord | None = None
    if decision.intent == "migrate_to_safe":
        if wallet is None or safe_address is None:
            raise RuntimeError(
                "reasoner returned migrate_to_safe but no wallet/safe_address was "
                "supplied to run_cycle; refusing to act without a destination."
            )
        action = migrate_to_safe(
            wallet,  # type: ignore[arg-type]
            safe_address,
            value_wei,
            dry_run=dry_run,
            audit_log=audit_log,
        )

    return CycleReport(breaches=breaches, decision=decision, action=action)


__all__ = ["CycleReport", "run_cycle"]
