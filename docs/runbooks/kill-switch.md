# Runbook: kill switch — authority and transaction-state semantics

Status: **mechanism live (env var); authority model is an OPEN DECISION.**
Written 2026-06-28 after an external review flagged two gaps: who is allowed to
press it, and what it actually affects for an in-flight transaction.

## What the kill switch is

A single control that halts all signing. Today it is an environment variable
checked at the top of `validate_or_die` (`napg/agentshield/pipeline.py`), before
any stage runs and before any wallet method is touched:

```bash
# engage
fly secrets set -a <agent-app> NAPG_KILL_SWITCH=1
# release
fly secrets unset -a <agent-app> NAPG_KILL_SWITCH
```

When engaged, every `validate_or_die` call raises `ValidationFailure` and a
`validation` row lands in the audit log with `kill_switch_engaged: true`, so the
halt is itself auditable.

Phase 5 replaces the env var with a **signed-message** variant (the wrapping API
stays the same so callers and tests do not change).

---

## What it does NOT do: in-flight transactions

The kill switch gates the *decision to sign*. It cannot recall a transaction
that has already left the agent. Reason about it as a state machine:

| State | Meaning | Effect of engaging the kill switch |
|---|---|---|
| **Constructed** | `TxIntent` built, not yet validated | Blocked — `validate_or_die` raises before signing |
| **Signed** | CDP MPC has signed; not yet broadcast | **Cannot recall.** If broadcast follows, it may land. The agent should not reach this state with the switch on (it is checked pre-sign), but a switch flipped *during* the sign round-trip is a genuine race |
| **Submitted** | Broadcast to the RPC / mempool-equivalent | Cannot recall. On Base (no public mempool, fast inclusion) the window is short but non-zero |
| **Included** | In a block | Settled; the switch is irrelevant |
| **Confirmed** | Final | Settled |

**The race (review #9):** a switch flipped between the pre-sign check and the
broadcast can still let one transaction land. Mitigations: (1) the agent signs
one action per cycle, so the exposure is at most one in-flight tx; (2) the dust
caps bound that one tx; (3) for a true emergency stop, also revoke the CDP API
key (see [key-compromise.md](key-compromise.md)) — that stops signing at the
source, not just at the agent's gate.

Do not assume "kill switch on" means "nothing can land." It means "nothing new
will be *initiated*."

---

## Authority — OPEN DECISION

Today: anyone with `fly secrets` / host access can engage or release it. That is
acceptable for solo-dev testnet but **must be decided before mainnet.** The
review's point: most crypto losses are operational, and an unguarded kill switch
(or one only one person can reach) is itself a risk.

Options to choose from:

- **Solo operator** (status quo) — simplest; single point of failure and single
  point of control.
- **2-of-3 / 3-of-5 security council** — a signed-message kill switch (Phase 5)
  verified against a small allowlist of authorised keys; engaging needs a quorum,
  but *releasing* should arguably need the same quorum so one party cannot
  silently re-enable signing.
- **Asymmetric**: any one council member can *engage* (fail safe — make stopping
  easy), but releasing needs a quorum (make resuming deliberate).

Recommendation to decide on: **asymmetric** — engage is 1-of-N, release is
M-of-N. Stopping should never be gated; resuming should be.

The same authority model should cover **key rotation** and **treasury movement**
(see [key-compromise.md](key-compromise.md) and the Phase 5 treasury policy).

## Drill

A kill-switch drill is a Phase 2 sign-off item (executed on testnet) and a
Phase 5 mainnet item. Re-run it whenever the mechanism changes (e.g. when the
signed-message variant lands).
