"""AgentShield: 4-stage validation pipeline gating every signing path.

Public entry point is `validate_or_die(intent)`. Every action that touches a
wallet must route through this module — the CI grep test that lands with
substep "Wire into actions.py" fails the build if any other code path calls
`wallet.sign*`, `wallet.send*`, `wallet.invoke*`, or `wallet.native_transfer`
outside `napg.agentshield` and its tightly-scoped callers.

The pipeline writes a `validation` audit row for every invocation (pass or
fail) so the audit log is the forensic record. The kill-switch
(`NAPG_KILL_SWITCH=1`) fails closed before any stage runs.

Stages land incrementally during Phase 2; until all four exist the default
stage callables raise `NotImplementedError` and `validate_or_die` fails
closed in production. Tests inject lightweight fakes via the `intent_judge=`,
`policy=`, `tenderly=`, and `honeypot=` keyword args.
"""

from napg.agentshield.pipeline import (
    StageResult,
    TxIntent,
    ValidationFailure,
    ValidationResult,
    validate_or_die,
)

__all__ = [
    "StageResult",
    "TxIntent",
    "ValidationFailure",
    "ValidationResult",
    "validate_or_die",
]
