# Runbook: external infrastructure outage

Status: **Tenderly behaviour is an OPEN DECISION; the rest is documented current
behaviour.** Written 2026-06-28 after an external review identified correlated
dependency failure as the sharpest pre-mainnet risk.

NAPG depends on several external services. Each failure mode below states the
*current* behaviour and, where a choice is needed, the decision to make before
mainnet. See [dependency-register.md](../dependency-register.md) for the full
list and criticality.

---

## Tenderly (AgentShield Stage 3) — THE key decision

**Current behaviour:** Stage 3 fails closed on any Tenderly transport error
(`stages/tenderly.py` raises `passed=False` on `httpx.HTTPError` / non-200). So
if Tenderly is unavailable, **all signing halts.**

**Why this is the sharpest risk:** NAPG exists to migrate funds to safety when
infrastructure is failing. But a *correlated* outage — market stress at the same
time Tenderly is degraded — would block the very `migrate_to_safe` action the
agent is for. A fail-closed gate meant to stop theft would also stop the rescue.

This is a genuine trade-off, not a bug. Failing closed is correct against a
*compromised* simulator; it is wrong against an *absent* one when the action is
the safety migration. The migration is the lowest-risk action in the system: a
native transfer to a pre-pinned, allowlisted safe address, already bounded by
Stage 2 dust caps.

**DECISION (needed before mainnet) — pick one:**

1. **Fallback simulator.** Primary Tenderly, fallback to a local `anvil` fork
   simulation for the state-diff check. Removes the single point of failure;
   adds a simulation dependency to run/maintain.
2. **Controlled migration override.** Keep Stage 3 fail-closed for *all* actions
   except `migrate_to_safe` to the allowlisted safe address; for that one action,
   a Tenderly outage degrades Stage 3 to a documented, audited override (still
   gated by Stage 2 caps + the destination allowlist + a distinct operator
   authorisation). Smallest change; narrowly scoped to the rescue path.
3. **Accept the risk.** Document that during a Tenderly outage the agent cannot
   migrate, and rely on a manual operator migration. Simplest; weakest.

Recommendation to decide on: **option 2** for launch (narrow, auditable, scoped
to the one action that can tolerate a degraded sim), with **option 1** as the
durable Phase 5 answer. Do not ship mainnet on option 3 silently.

---

## Base L2 outage (sequencer down / not producing blocks)

**Current behaviour:** the RPC heartbeat detects it (stale block age, latency)
and raises breaches; the reasoner may decide to `migrate_to_safe` — but the
migration **cannot be submitted if Base is not producing blocks.** The "safe
state" is on Base, so during a full L2 outage it is unreachable on-chain.

This is a network-level limitation NAPG cannot engineer around: the L1
force-include escape hatch is the network's censorship backstop, not an
application primitive we drive. Document it plainly:

- During a Base outage, the agent's on-chain options are frozen along with
  everyone else's. NAPG's value in that window is *detection + alerting + a
  recorded decision*, not on-chain action.
- When Base resumes, the queued decision should re-evaluate against fresh state
  rather than blindly replaying a stale intent (tie-in to the
  `max_simulation_age_seconds` freshness gate, Group E review #1).

## RPC provider degradation (not a full outage)

Handled in-band: `monitor/resilience.py` provides a token-bucket limiter, a
consecutive-failure circuit breaker, and `FailoverRpcHeartbeat` failing over to
`BASE_*_RPC_URL_FALLBACK` when set. Set the fallback in prod. Aerodrome/Morpho
are single-provider today (revisit with multi-RPC in Phase 5).

## x402 protected submission endpoint (Group E)

Fail-closed: if the configured submission endpoint is unreachable, **halt signing
and alert — never fall back to an unprotected path** (Group E review #2). No
second protected RPC exists for Base today, so failover is halt-and-alert.

## Anthropic (reasoning + Stage 1 Intent Judge)

If the Anthropic API is down, the agent cannot produce a `Decision`, so it takes
no autonomous action — fail-safe (no action is the safe default). Note both the
reasoner and the Stage 1 Intent Judge use the model, so this is a single
dependency for two layers; Stage 2 (deterministic) is unaffected and still bounds
any action that *does* get proposed. The LLM has zero authority over funds by
construction — see the AgentShield pipeline.

---

## The five questions this runbook answers (from the review)

1. **Tenderly down 24h?** -> All signing halts today; pick a DECISION above.
2. **Base down 6h?** -> Detection + recorded decision only; on-chain action
   frozen network-wide; re-evaluate on resume.
3. **MPC key compromised?** -> [key-compromise.md](key-compromise.md).
4. **Who presses the kill switch?** -> [kill-switch.md](kill-switch.md).
5. **LLM pathological?** -> Bounded by deterministic AgentShield + dust caps;
   the model can only propose, never authorise.
