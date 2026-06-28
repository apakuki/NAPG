# Runbook: treasury emergency migration

Status: **procedure drafted; the degraded-override path is decided
(2026-06-28) but not yet implemented.** Covers moving treasury funds to safety,
both the normal autonomous path and the degraded path when AgentShield's
dependencies are down.

`migrate_to_safe` (native transfer to the pre-pinned `NAPG_SAFE_CONTRACT_ADDRESS`)
is the only fund-moving action NAPG performs. This runbook is when, who, where,
rollback, and comms.

## Triggers

A migration is initiated when the decision cycle classifies state as requiring it
— driven by Service Level Breaches (reorg, sustained RPC degradation, peg break,
liquidity collapse, market-utilisation/staleness), per the reasoning matrix. A
reorg is the top-priority trigger. The agent proposes; AgentShield gates;
migration is the safe default when the chain may have un-settled state.

Operator-initiated migration is also valid (`napg migrate --execute`) — e.g. a
human seeing a threat the monitors don't cover yet.

## Path A — normal (autonomous, all gates healthy)

1. Reasoner returns `migrate_to_safe`; `validate_or_die` runs all four stages.
2. Stage 2 caps + denylist/allowlist + Stage 3 Tenderly sim + Stage 4 honeypot
   all pass.
3. Wallet signs; tx submitted; `action` row recorded with the receipt.
4. No human in the loop — this is the designed autonomous rescue.

## Path B — degraded controlled override (Tenderly/sim unavailable)

Per the locked decision in [infra-outage.md](infra-outage.md). Use **only** when
Stage 3 cannot run because Tenderly is unreachable, and the action is the safety
migration. Every condition must hold:

1. **Confirm the trigger is real**, not a false positive — see
   [false-positive-breach.md](false-positive-breach.md). Do not override on a
   monitoring artefact.
2. **Confirm Tenderly is genuinely down** (not a transient blip): the sim gate is
   the thing you are bypassing, so be sure it is actually absent.
3. **Destination is the allowlisted safe address** — never a new address under
   pressure. If the safe address itself is suspect, stop and escalate.
4. **Native transfer only** — no swaps, approvals, contract calls. Value within
   Stage 2 caps.
5. **Human approval** (the override's authorisation, distinct from the agent).
   Governance for who can authorise: [kill-switch.md](kill-switch.md) authority
   model (same council).
6. A `migration_override` audit row lands **before** signing, naming the operator
   and the reason.

The override buys back the rescue, not autonomy. It is a rarely-used backstop;
the Phase 5 anvil-fork fallback is the durable fix that removes the need for it.

## Path C — chain frozen (Base not producing blocks)

No on-chain action is possible (see [infra-outage.md](infra-outage.md)). Record
the decision, alert, and re-evaluate against fresh state when Base resumes — do
not blind-replay a stale intent.

## Destination

Always `NAPG_SAFE_CONTRACT_ADDRESS` — pre-pinned, allowlisted, and (for a
contract safe) verified to accept value + the Builder Code suffix. The safe
address is config and change-controlled; rotating it is a deliberate, reviewed
act, never done mid-incident.

## Rollback

A migration moves funds *to* safety; "rollback" means moving them *back* once the
threat clears, which is itself a normal `migrate`/transfer subject to the full
gates — there is no fast-path reversal and there should not be. Treat the
post-incident return of funds as a separate, unhurried, fully-validated action.

## Communications

- Status page entry (transparent, with whatever delay is responsible).
- Incident channel timeline.
- For Guardian Mode subscribers whose positions are affected: a notification once
  the migration is confirmed.

## Path B is implemented

`napg.override` (+ `build_migration_override_validator`). Operator two-step:

```bash
# step 1 — arm (manual approval; records migration_override_armed)
napg override arm --approver <you> --justification "tenderly down during <event>"
# step 2 — after the two-step wait (migration_override_wait_seconds), execute
napg override execute --amount-eth <amt> --execute
```

The override substitutes only the Tenderly stage; Stage 2 caps, denylist,
Intent Judge, Honeypot, and the kill-switch all still apply, and the validator
re-checks the two-step wait + TTL at execution. `--execute` is required to move
funds (omit it for a dry run). The durable Phase 5 replacement is the local
anvil-fork fallback, after which this override becomes a rarely-used backstop.
