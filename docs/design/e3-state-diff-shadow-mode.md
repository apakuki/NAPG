# E3 design: Stage 3 swap state-diff parser (shadow-mode-first)

Status: **design only; not built.** Written 2026-06-28 after a review crystallised
why this code is different from everything else in Group E.

## The reclassification

E1 (slippage floor) and E2 (execution-quality dataset, token universe) are
*observability and policy* code. The Stage 3 swap state-diff parser is not. It
answers "did the simulation say I will receive at least `min_out`?" — and that
answer **authorises a signature**:

```
Tenderly says: you will receive X
   -> X >= min_out
   -> sign the swap
```

A parser bug therefore directly moves funds. It is **authorization code**, in the
same tier as the signing pipeline, the MPC wallet, and the kill switch — not
ordinary business logic. The biggest risk in Group E is no longer MEV itself; it
is **incorrect interpretation of simulation data becoming an authorization
decision.** This document sets the bar accordingly.

## Hard requirements (all must hold before the parser is authoritative)

### R1 — No generic parser. Start with one pair.
The first parser supports **Aerodrome USDC/USDT only**. Add WETH and cbBTC
afterwards, one at a time, each with its own fixtures. A general "parse any
swap's output" routine is out of scope until the constrained cases are proven.
Mirrors the swap token universe (`swap_token_allowlist`, default empty).

### R2 — Store the raw Tenderly payload for every simulation.
Persist `{simulation_id, raw_response, parsed_response}` (audit kind
`swap_simulation`). When a weird case surfaces months later, it can be replayed
against a new parser version. Without the raw payload, a parser bug is
unreproducible.

### R3 — Shadow mode first. The parser does not authorise until proven.
Before any swap is signable on the strength of the parse:
1. Run the parser on every candidate simulation.
2. Record `parsed_simulated_out` next to the eventual `realized_out`.
3. **Never sign on it.** Swap authorisation stays frozen.
4. Collect a threshold of live samples (target: >= 1 week AND >= 1000
   simulations across the supported pair) and compare parsed-vs-realized.
Only after a written security review of that data does the parser become
authoritative. This is the single most important requirement.

### R4 — Property / fuzz tests; fail closed on everything unexpected.
Fuzz the `asset_changes` shape against at least: multiple transfers, duplicate
token transfers, extra transfers, missing recipient, zero transfers, unexpected
decimals, and recipient mismatch. The parser must return "cannot determine
output" (-> fail closed) on anything it does not unambiguously understand. A
parse it is not certain about is a parse it must refuse.

### R5 — Version-pin the Tenderly response shape.
Third-party APIs evolve. Check a `schema_version` / required-fields fingerprint
on every response and **reject unknown formats** (fail closed) rather than
parsing them optimistically. A silent shape change must stop signing, not
misread balances.

## Token universe must capture token *behaviour*, not just address

The E2 `swap_token_allowlist` is addresses only. Before swaps are enabled it
should carry behaviour so excluded token types are explicit, e.g.:

```toml
[[swap_token]]
address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # USDC
symbol = "USDC"
decimals = 6
token_type = "vanilla"
enabled = true

[[swap_token]]
address = "0x..."  # stETH
symbol = "stETH"
token_type = "rebasing"
enabled = false
```

Explicitly excluded token classes (the parser must never trust their deltas):
**fee-on-transfer, rebasing, wrapper, ERC-777 (transfer hooks create unexpected
flows), and upgradeable tokens (behaviour can change underneath us).** Only
`token_type = "vanilla"` + `enabled = true` is parseable.

## Execution-record context fields (add when the swap action lands)

The E2 `SwapExecution` dataset is the right shape; extend it with cheap context
so later questions are answerable:

- `block_number` — was it a specific block?
- `pool` — did one pool behave differently?
- `rpc_provider` — did it only happen on one RPC?
- `submission_endpoint` — protected vs default path.

These are tiny and pay off the first time you debug an outlier.

## Strategic sequence (do not collapse these steps)

```
merge E2 (#35)            [done]
  -> freeze swap authorisation
  -> implement E3 parser in SHADOW MODE (R1-R5), store raw payloads
  -> collect live parsed-vs-realized data (>=1 week, >=1000 sims)
  -> written security review of the data + the parser
  -> only then: parser becomes authoritative, swaps signable
  -> only then: MEV-protected submission endpoint
```

Explicitly **not** allowed: `E3 merged -> production signing`. Merging the parser
must not, by itself, enable swap authorisation.

## Why the submission endpoint waits

The endpoint is not the dangerous part; the dangerous part is the whole chain
`quote -> simulation -> submission -> execution` being trusted. All four must be
observable (the E2 dataset + E3 shadow data) before any of it authorises a
signature. The protected endpoint lands last, once the rest is proven.

## References
- [docs/design/phase-4-mev.md](phase-4-mev.md) — the MEV gate design.
- [PLAN.md Phase 4 Group E](../../PLAN.md#phase-4-wk-5-monetization-and-attribution).
- [docs/threat-models/phase-2.md](../threat-models/phase-2.md) — AgentShield, where
  this parser's threat model will be folded in at its security review.
