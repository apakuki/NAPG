# Dependency register

Status: **living document.** Started 2026-06-28 after an external review noted
that NAPG has already been forced to pivot twice by upstream change (USDbC and
Seamless wind-downs), so the external dependencies and their exit plans should be
tracked explicitly rather than rediscovered under pressure. Enriched with
Owner / Detection / RTO columns per the second-round review.

Columns: **Owner** (who controls it) · **Criticality** (blast radius: HIGH =
funds/safety, MEDIUM = revenue/UX, LOW = analytics) · **Detection** (how we learn
it failed) · **Exit / mitigation** · **RTO** (target time to restore the function,
by our own action — "undefined" where we cannot).

## Protocols monitored (the product surface)

| Dependency (role) | Owner | Criticality | Detection | Exit / mitigation | RTO |
|---|---|---|---|---|---|
| Aerodrome USDC/USDT via 0x (liquidity + peg probe) | DEX / DAO | Medium | Probe error / peg breach / liquidity drop | Repoint pair in config (pair-agnostic). Precedent: USDbC -> USDT 2026-05-19 | ~1h (config) |
| Morpho Blue WETH-USDC, cbBTC-USDC (lending state) | DAO | Medium | Poll error / governance monitoring | Repoint markets in config (market-id driven). Precedent: Seamless -> Morpho 2026-05-19 | ~1h (config) |

The pivots above are *why* this register exists: a monitored protocol changing is
a when, not an if. Keep monitor targets in config, never hard-coded.

## Infrastructure (funds + safety path)

| Dependency (role) | Owner | Criticality | Detection | Exit / mitigation | RTO |
|---|---|---|---|---|---|
| Coinbase CDP — MPC wallet + TEE signing | Coinbase | **High** | Signing call errors | No alternative signer by design. Outage is fail-safe (no action). Leak: [key-compromise.md](runbooks/key-compromise.md) | Outage: vendor-bound. Compromise: ~1h (rotate) |
| Base — L2 / sequencer | Coinbase | **High** | RPC heartbeat (block age / latency) | Network-level; cannot engineer around. Detect + record + re-evaluate on resume. [infra-outage.md](runbooks/infra-outage.md) | **Undefined** (max acceptable outage assumed 24h) |
| Circle / USDC — treasury + x402 asset | Circle | **High** | Peg probe; external depeg/freeze news | [treasury-policy.md](treasury-policy.md): concentration limits + max acceptable permanent loss (5%) | Depeg: vendor-bound; mitigated by policy |
| Tenderly — AgentShield Stage 3 sim | Tenderly | **High** | API health (transport error / non-200) | **DECIDED:** degraded controlled override for the safety migration; anvil-fork fallback in Phase 5. [infra-outage.md](runbooks/infra-outage.md) | Override: immediate (human-gated). Anvil: Phase 5 |

## Infrastructure (reasoning, revenue, UX)

| Dependency (role) | Owner | Criticality | Detection | Exit / mitigation | RTO |
|---|---|---|---|---|---|
| Anthropic — reasoner + Stage 1 Intent Judge | Anthropic | Medium | API errors | No Decision = no action (fail-safe). Stage 2 deterministic backstop; LLM has zero fund authority. Judge on a different Claude model (decision 6) | Vendor-bound; fail-safe meanwhile |
| 0x API — Aerodrome quote source | 0x | Medium | Probe error / quote anomaly | Rate-limit + circuit breaker (`resilience.py`); card degrades. Multi-source pricing is review #13 (not yet built) | ~mins (breaker) |
| Farcaster / SIWF relay — auth | Farcaster | Medium | Relay errors on login | Existing HttpOnly sessions keep working; logins retry | Vendor-bound (existing users unaffected) |
| x402 facilitator — on-chain settlement | TBD | Medium | Settlement vs audit reconciliation (4.14) | Deferred (Group B verifies + accounts; settlement is facilitator wiring) | Phase 4/5 |
| Base.dev / ERC-8021 indexer — attribution | Coinbase | Low | Attribution counts | No fund impact; suffix is inert calldata; registration carried to Phase 5 | n/a |
| Fly.io — host | Fly.io | Medium | Health checks / uptime | Two-app topology; audit DB on a Fly volume + backups; Phase 5 host review | Vendor-bound; restore from backup |

## Concentration notes (review #5, #14)

- **Treasury concentration is now defined as policy** (not deferred) in
  [treasury-policy.md](treasury-policy.md): `max_acceptable_permanent_loss` (5%),
  per-protocol cap (40%), and the 24h Base-outage assumption that makes 100%
  on-Base USDC acceptable *for launch*. Enforcement code is Group F; the limits
  are architecture now because they set the migration/outage/rescue assumptions.
- **Stacked HIGH dependencies on the Coinbase/Circle stack** (CDP + Base + USDC).
  Inherent to building on Base and a deliberate choice, but a single-ecosystem
  incident is correlated across signing, settlement, and treasury. State this in
  any risk disclosure rather than treating the three as independent.

## Review the register

Re-check on every monitored-protocol change, every new external dependency, and
at each phase sign-off. Out of scope here but flagged by the review:
**legal/regulatory** posture (autonomous agent + payments + assurance reports +
treasury yield) is a business decision to take before traction, not an
engineering control.
