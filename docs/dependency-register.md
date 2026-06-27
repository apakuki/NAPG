# Dependency register

Status: **living document.** Started 2026-06-28 after an external review noted
that NAPG has already been forced to pivot twice by upstream change (USDbC and
Seamless wind-downs), so the external dependencies and their exit plans should be
tracked explicitly rather than rediscovered under pressure.

"Criticality" = blast radius if the dependency degrades or disappears.
Funds-at-risk and safety-action dependencies are HIGH; revenue/UX are MEDIUM;
analytics/attribution are LOW.

## Protocols monitored (the product surface)

| Protocol | Role | Criticality | Failure mode | Exit / mitigation |
|---|---|---|---|---|
| Aerodrome (USDC/USDT via 0x) | Liquidity-depth + peg probe | Medium | Pool wound down or repriced (cf. USDbC) | Repoint the pair in config; the probe is pair-agnostic. Precedent: USDC/USDbC -> USDC/USDT, 2026-05-19 |
| Morpho Blue (WETH-USDC, cbBTC-USDC) | Lending-market state poller | Medium | Market deprecated / oracle change (cf. Seamless) | Repoint markets in config; monitor is market-id driven. Precedent: Seamless -> Morpho Blue, 2026-05-19 |

The pivots above are *why* this register exists: a monitored protocol changing is
a when, not an if. Keep monitor targets in config, never hard-coded.

## Infrastructure (funds + safety path)

| Dependency | Role | Criticality | Failure mode | Exit / mitigation |
|---|---|---|---|---|
| Coinbase CDP (MPC wallet + TEE signing) | All signing authority | **High** | Outage = no signing; credential leak = [key-compromise.md](runbooks/key-compromise.md) | No alternative signer by design (MPC-only). Outage is fail-safe (no action). Compromise has a recovery playbook |
| Base (L2 / sequencer) | The chain itself | **High** | Sequencer down = no on-chain action, safe state unreachable | Network-level; cannot engineer around. Detect + record + re-evaluate on resume. [infra-outage.md](runbooks/infra-outage.md) |
| Circle / USDC | Treasury + x402 settlement asset | **High** | Depeg, freeze, regulatory action | Treasury concentration policy (Group F, pending): max single-asset / single-issuer exposure. Currently testnet only |
| Tenderly (AgentShield Stage 3) | Simulation gate before signing | **High** | Outage halts all signing — incl. the safety migration (correlated-failure risk) | OPEN DECISION in [infra-outage.md](runbooks/infra-outage.md): fallback anvil sim vs controlled migration override |

## Infrastructure (reasoning, revenue, UX)

| Dependency | Role | Criticality | Failure mode | Exit / mitigation |
|---|---|---|---|---|
| Anthropic (Claude) | Reasoner + Stage 1 Intent Judge | Medium | Outage = no Decision = no action (fail-safe). Single dep for two layers | Stage 2 is deterministic and bounds any proposed action; LLM has zero fund authority. Direct SDK, swappable |
| 0x API | Aerodrome quote source | Medium | Outage / bad quote | Rate-limit + circuit breaker (`resilience.py`); card degrades, not 500. Multi-source pricing is a review #13 hardening (TWAP/Chainlink/DEX deviation checks) — not yet built |
| Tenderly (as above) | — | — | — | — |
| Farcaster / SIWF relay | Auth | Medium | Relay down = no new logins | Existing sessions keep working (HttpOnly cookie); login retries |
| Base.dev / ERC-8021 indexer | Builder Code attribution | Low | Attribution not counted | No fund impact; suffix is inert calldata. Registration carried to Phase 5 |
| x402 facilitator | On-chain settlement of verified payments | Medium | Verified payment not settled on-chain | Deferred (Group B verifies + accounts; settlement is the facilitator wiring). Reconciliation (4.14) catches gaps |
| Fly.io | Host | Medium | Host outage = agent down (fail-safe) | Two-app topology; Phase 5 production host decision. Audit DB on a Fly volume + backups |

## Concentration notes (review #5, #14)

- **Treasury** is 100% native USDC by default today. Before any real treasury
  balance, write a concentration policy (Group F): `max_single_issuer_exposure`,
  `max_protocol_exposure`, and a stated **maximum acceptable permanent loss** —
  yield is never free (smart-contract / protocol / depeg / governance /
  regulatory risk).
- **Stacked HIGH dependencies on the Coinbase stack** (CDP + Base + USDC are all
  Coinbase/Circle-adjacent). This is inherent to "building on Base" and is a
  deliberate product choice, but it means a single-ecosystem incident is
  correlated across signing, settlement, and treasury. Worth stating in any
  risk disclosure.

## Review the register

Re-check on every monitored-protocol change, every new external dependency, and
at each phase sign-off. Out of scope here but flagged by the review:
**legal/regulatory** posture (autonomous agent + payments + assurance reports +
treasury yield) is a business decision to take before traction, not an
engineering control.
