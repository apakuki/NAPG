# Phase 4 design note — MEV exposure and protection for token actions

Status: design (pre-implementation). Scope: the MEV exposure NAPG takes on when
the Phase 4 token-handling surfaces land (x402-paid actions, Guardian Mode
position management, and any swap the agent performs), and the protections to
build into them before they ship.

This is a design note, not a sign-off threat model. The matching
[PLAN.md Phase 4](../../PLAN.md) substeps (Builder Code, x402, Guardian Mode)
have not been built. The point of writing this now is to put MEV on record as a
first-class concern *before* the swap surfaces exist, so the protections land
with the actions rather than being retrofitted. The eventual Phase 4 threat
model (`docs/threat-models/phase-4.md`) will fold the conclusions here into its
sign-off checklist.

## 1. Framing: which layer NAPG is in

The Base MEV landscape — latency/FCFS races, the centralized-sequencer whitelist,
the Neutrality Principles, the TEE/ZK sequencing roadmap — is a property of the
*network's transaction-ordering layer*. NAPG does not live in that layer. It is
an application-layer agent that consumes Base the way any other user does:
read-path probes (heartbeat, a 0x price quote, a Morpho `view` call) and, today,
exactly one write path.

So NAPG does not implement, alter, or police network-level MEV. What it can and
must do is manage the MEV exposure of *its own transactions*. Everything below is
about that, not about Base's sequencer.

### What NAPG inherits from Base (and therefore does not solve)

- **No public mempool / FCFS ordering.** Base has no public bid-for-position
  mempool, so the classic Ethereum sandwich (bid around a pending swap visible in
  the mempool) does not have the same surface. NAPG relies on this; it does not
  re-create it.
- **Neutrality Principles.** Unbiased sequencing and data discretion are
  Coinbase's guarantees, not NAPG's to verify. NAPG is a beneficiary.
- **The escape hatch** (force-include via L1) is the network's censorship
  backstop. NAPG's `migrate_to_safe` is the *application-layer* analogue — get to
  a safe state when the chain misbehaves — but they are different mechanisms at
  different layers.

The one network-level MEV vector NAPG actively watches is reorgs: the reasoning
matrix treats any reorg as the top-priority `migrate_to_safe` trigger
([`reasoning.py`](../../agent/napg/reasoning.py), rule 2). On Base's centralized
sequencer reorgs are rare, but the posture — "a reorg means settled transactions
may be un-settled; there is no safe assumption to operate under" — is the most
MEV-defensive stance in the system. That is defensive monitoring, not trade
protection.

## 2. Current exposure (Phases 1-3): effectively none

NAPG's only action today is
[`migrate_to_safe`](../../agent/napg/actions.py), a **native ETH transfer** to a
pre-pinned safe address. A native transfer:

- has no DEX interaction, so there is no pool to manipulate;
- has no slippage surface and no price, so there is nothing to sandwich;
- carries `data == "0x"`, which AgentShield Stage 2 requires and Stage 4
  trivially passes ([`stages/policy.py`](../../agent/napg/agentshield/stages/policy.py),
  [`stages/honeypot.py`](../../agent/napg/agentshield/stages/honeypot.py)).

Its MEV exposure as a *trader* is therefore near-zero, which is exactly why
nothing in the current codebase addresses MEV — there is nothing to protect yet.
That changes the moment NAPG swaps or moves tokens.

## 3. The gap: Phase 4 token surfaces

Phase 4 introduces actions that touch tokens and prices:

- swaps (e.g. rotating a monitored position to a safe asset, or any DEX route);
- x402-paid flows that may settle in USDC;
- Guardian Mode position management.

At that point NAPG becomes a value-bearing trader on a public chain and inherits
real adverse-execution risk: latency searchers landing an arbitrage immediately
after its swap, fee-on-transfer / rebasing surprises, and stale-quote execution.
None of the current code protects against this:

- **No slippage floor is enforced.** The 0x probe already parses `minBuyAmount`
  ([`aerodrome.py`](../../agent/napg/monitor/aerodrome.py)), but purely for
  *monitoring* the quote. It is not wired into any swap as an on-chain `minOut`.
- **No MEV-protected submission.** A swap would go through the same default RPC
  path as everything else; there is no private/MEV-aware submission endpoint.
- **No post-trade execution-quality check.** Nothing compares realized output
  against the quote that justified the trade.

## 4. Design: make MEV a first-class gate

The protections map cleanly onto seams that already exist. The guiding rule is
the same one the rest of AgentShield follows: **fail closed** — a swap intent
with no slippage floor must not be signable.

### 4.1 Stage 2 (Policy): mandatory slippage floor

Extend `TxIntent` with the fields a swap declares — `min_out_wei` (or
`min_buy_amount`), `quoted_out_wei`, and the token pair — and add a check to the
Stage 2 policy callable
([`stages/policy.py`](../../agent/napg/agentshield/stages/policy.py)):

- a swap intent **must** carry a non-null `min_out_wei`;
- `min_out_wei` must be within a configured maximum slippage from
  `quoted_out_wei` (e.g. `max_slippage_bps`, new field in
  [`config/policy.toml`](../../agent/config/policy.toml), signed like the rest);
- reject (fail closed) if either is missing or the implied slippage exceeds the
  cap.

This makes "a swap with no protection" structurally unsignable, the same way a
denylisted destination or an over-cap value is today. Because `policy.toml` is
Ed25519-signed, the slippage ceiling gets the same tamper-evidence as the per-tx
cap.

### 4.2 Stage 3 (Tenderly): execution-quality state-diff

Stage 3 already simulates the tx
([`stages/tenderly.py`](../../agent/napg/agentshield/stages/tenderly.py)) but
currently reads only four scalar fields and defers state-diff parsing. For a
swap, activate the deferred state-diff path to assert the *simulated* received
amount is `>= min_out_wei`. This catches adverse execution (and a lying or stale
quote) before signing, independent of what the submission path does. It is the
natural place to land the state-diff work that the Phase 2 threat model already
lists as deferred.

### 4.3 Submission path: MEV-protected endpoint

When the swap action submits (the token-action analogue of
[`actions.py`](../../agent/napg/actions.py)), route it through an
MEV-protected/private submission endpoint rather than the default RPC, configured
via a new `Settings` field ([`config.py`](../../agent/napg/config.py)). This keeps
the native-transfer path unchanged and confines the new dependency to the swap
surface. Submission still happens only after `validate_or_die` passes, so the CI
invariant (no signing outside `napg.actions` / `napg.agentshield`) is unaffected.

### 4.4 New probe + breach: realized slippage as a Service Level Breach

Add a post-trade (or periodic) probe that compares realized execution against the
quote and emits a `realized_slippage_bps_max` breach via the rules engine
([`policy/breaches.py`](../../agent/napg/policy/breaches.py)), with the threshold
in [`config/breaches.toml`](../../agent/config/breaches.toml). This turns MEV loss
into something the dashboard and the append-only audit log capture as first-class
assurance data — consistent with NAPG's whole premise (every autonomous outcome
is audit-recoverable), and it gives Guardian Mode subscribers a real execution-
quality signal.

## 5. Threats and mitigations (token-action surface)

| Threat | Mitigation |
|---|---|
| Sandwich / adverse execution on a NAPG swap | Stage 2 mandatory `min_out_wei` + `max_slippage_bps`; on-chain minOut reverts a bad fill |
| Latency searcher arbs immediately after the swap | MEV-protected submission endpoint (4.3); minOut bounds the loss regardless |
| Stale or hostile quote justifies a bad trade | Stage 3 state-diff asserts simulated out >= minOut before signing |
| Fee-on-transfer / rebasing token surprises execution | Stage 4 honeypot BUY-then-SELL (already stubbed) + Stage 3 state-diff |
| MEV loss goes unnoticed | `realized_slippage_bps_max` breach -> audit log + dashboard |
| Swap submitted with no protection at all | Fail-closed Stage 2: a swap intent without a slippage floor is unsignable |

## 6. Accepted risks / deferred

- **Encrypted/private ordering** is a network property NAPG cannot provide; it can
  only choose a protected submission endpoint. If Base's TEE/ZK sequencing lands,
  NAPG benefits automatically with no code change.
- **Toxic-MEV mitigation at L1** is out of scope by construction — NAPG is not a
  sequencer.
- **Cross-block / multi-tx MEV** (e.g. a position unwound over several txs) is not
  addressed by per-tx minOut; if Guardian Mode performs multi-leg unwinds, a
  follow-up note should cover batch-level execution accounting (EIP-5792 batch is
  the natural unit).
- This note is **design-only**; none of section 4 is built. Each item becomes a
  Phase 4 substep with its own tests and a line in the Phase 4 threat model.

## 7. Open questions for Phase 4 kickoff

- Which MEV-protected submission endpoint(s) are available and appropriate for
  Base mainnet at build time, and what is the fallback if one is degraded
  (reuse the circuit-breaker pattern from
  [`resilience.py`](../../agent/napg/monitor/resilience.py))?
- Does the first token action actually need a swap, or can the safe-rotation be
  expressed as transfers of already-held assets (which keeps exposure near-zero
  for longer)? Prefer the lowest-MEV action that meets the product need.
- What `max_slippage_bps` default is tight enough to bound loss but loose enough
  not to revert legitimate stable-pair rotations? Tune against observed Aerodrome
  USDC/USDT spreads the existing probe already records.

## 8. References

- [docs/architecture.md](../architecture.md) — system overview and extension seams.
- [docs/threat-models/phase-2.md](../threat-models/phase-2.md) — AgentShield
  pipeline, including the deferred Tenderly state-diff work this note would
  activate for swaps.
- [PLAN.md](../../PLAN.md) — Phase 4 substeps (Builder Code, x402, Guardian Mode).
</content>
