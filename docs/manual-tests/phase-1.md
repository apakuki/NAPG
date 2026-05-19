# Manual test procedures — Phase 1 (Prototype and Logic Core)

Status: **skeleton.** Procedures fill in as monitors, reasoning, and migration land. Source-of-truth for what's being built: [PLAN.md Phase 1](../../PLAN.md#phase-1-wk-1-2-prototype-and-logic-core).

Prerequisites (once Phase 1 starts): `.env` filled in with `ANTHROPIC_API_KEY`, `BASE_SEPOLIA_RPC_URL`, `CDP_*` testnet wallet, `ZEROX_API_KEY`, `TENDERLY_*`. Testnet ETH in the agent wallet.

---

## 1.1 — RPC heartbeat against Base Sepolia

**Goal:** confirm Web3.py is hitting Base Sepolia and reporting latency, block height, and reorg state.

**Steps:**
```bash
# From agent/, with .env populated (BASE_SEPOLIA_RPC_URL=https://...)
uv run python -m napg heartbeat
# Run twice ~5s apart and compare block numbers; run again after ~30s.
```

**Expected:**
- [x] Output is JSON with `rpc_url`, `chain_id=84532`, `latency_ms`, `block.number`, `block.hash`, `block.parent_hash`, `reorg_detected=false`.
- [x] `block.number` advances between consecutive runs (Base Sepolia produces a block roughly every 2s).
- [x] `latency_ms` is reasonable for the geography of the configured RPC provider (single-digit-hundreds for a regional Alchemy/QuickNode).
- [x] `reorg_detected` stays `false` across a quiet window.

Verified 2026-05-18 against the rotated Alchemy Base Sepolia endpoint after the prior key was scrubbed and the app recreated.

---

## 1.2 — Aerodrome USDC/USDT pool probe

**Goal:** quoted USDC/USDT rate is on-peg and at least one of the routed sources is recognisably an Aerodrome variant when the pool is healthy.

The probed pair was originally USDC/USDbC, repointed to USDC/USDT on 2026-05-19 — see [PLAN.md "Resolved decisions"](../../PLAN.md#resolved-decisions-2026-05-16) for the rationale.

**Steps:**
```bash
# From agent/, with .env populated (ZEROX_API_KEY=...)
uv run python -m napg aerodrome
# Compare the quoted_rate against a block-explorer read of the Aerodrome
# USDC/USDT Slipstream pool (ratio = reserve_USDT / reserve_USDC).
```

The probe queries Base mainnet (chainId 8453) regardless of `NAPG_NETWORK`, because Aerodrome only exists on mainnet.

**Expected:**
- [x] Output is JSON with `chain_id=8453`, `liquidity_available=true`, `sell_amount=10000000000` (10k USDC at 6 decimals).
- [x] `quoted_rate` within 1% of the explorer-derived rate for the pool.
- [x] `peg_deviation_bps` is small (single digits) during a quiet, healthy window.
- [x] `sources` contains at least one Aerodrome variant (e.g. `Aerodrome_V3`, which is 0x's label for Aerodrome Slipstream) when the pool is the deepest source; if absent, capture the route in the runbook — it means another venue is currently clearing tighter than Aerodrome.

Verified 2026-05-19: live probe returned `peg_deviation_bps=6`, route `["Aerodrome_V3"]`, after pivoting the pair from USDC/USDbC to USDC/USDT (USDbC has wound down; see [PLAN.md "Resolved decisions"](../../PLAN.md#resolved-decisions-2026-05-16)). The earlier USDC/USDbC probe ran 2026-05-19 first and surfaced no Aerodrome in the route plus 15 bps deviation — that was the signal that drove the pivot.

---

## 1.3 — Morpho Blue market state (WETH-USDC, cbBTC-USDC)

**Goal:** utilisation and on-chain accrual staleness for the two monitored Morpho Blue markets match what the [Morpho app](https://app.morpho.org/base) shows for the same markets.

Originally this test was scoped to Seamless lending markets, but Seamless announced an orderly wind-down in April 2026 (web app offline 2026-06-30) and would not exist at NAPG's launch. We repointed to Morpho Blue on Base because Coinbase Loans uses Morpho Blue as its underlying lending primitive — it is the largest load-bearing lending surface on Base. See [PLAN.md "Resolved decisions"](../../PLAN.md#resolved-decisions-2026-05-16).

Oracle freshness (the second half of the original substep) is deferred to a follow-up: Morpho oracles are arbitrary `IOracle` contracts, not a single shared registry like `AaveOracle`, so freshness needs per-market introspection rather than one universal lookup.

**Steps:**
```bash
# From agent/, with .env populated (BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/...)
uv run python -m napg morpho
```

Cross-check each market against its page on app.morpho.org:
- WETH-USDC market: `https://app.morpho.org/base/market/0x8793cf302b8ffd655ab97bd1c695dbd967807e8367a65cb2f4edaf1380ba1bda/weth-usdc`
- cbBTC-USDC market (Coinbase Loans): `https://app.morpho.org/base/market/0x9103c3b4e834476c9a62ea009ba2c884ee42e94e6e314a26f04d312434191836/cbbtc-usdc`

Note: this hits **Base mainnet**, not Sepolia, regardless of `NAPG_NETWORK`. Morpho only exists on mainnet. With Alchemy you can use the same project key as the heartbeat endpoint, just swap the subdomain from `base-sepolia` to `base-mainnet`.

**Expected:**
- [x] Output is JSON with `chain_id=8453`, two `markets` entries (`WETH-USDC`, `cbBTC-USDC`).
- [ ] For each market, `total_supply_assets` and `total_borrow_assets` are within 1% of the figures shown in the Morpho UI for that market (the UI displays USDC totals; remember our output is in raw 6-decimal USDC units). _Manual cross-check against app.morpho.org pending._
- [ ] `utilization_bps` matches the UI's "Utilization" percentage (e.g. UI 78.3% ↔ `utilization_bps` between 7820 and 7840). _Manual cross-check pending._
- [x] `staleness_seconds` is small (typically under a few minutes) — Morpho accruals update on every interaction, so a low-activity market may show several minutes of staleness; flag anything above ~1 hour for follow-up.
- [x] `latency_ms` reasonable for a single RPC round trip with two contract reads.

Verified 2026-05-19 against live Morpho Blue on Base mainnet:
- WETH-USDC: $76.98M supply, $69.58M borrow, 9039 utilisation bps, 44s staleness
- cbBTC-USDC: $1.35B supply, $1.22B borrow, 9039 utilisation bps, 4s staleness (matches public "$1.4B+ cbBTC collateralized" reporting almost exactly)

First probe (before swapping the second market) returned `wstETH-USDC` at only $485 supply — that signal drove the swap to `cbBTC-USDC`. The pivot is recorded in [PLAN.md "Resolved decisions"](../../PLAN.md#resolved-decisions-2026-05-16).

---

## 1.4 — Breach threshold evaluation

**Goal:** flipping a single threshold below current state triggers a breach in the agent log.

**Steps:** _TODO when `napg.policy.breaches` lands._

**Expected:**
- [ ] A test config that sets `latency_ms_max` below the current measurement produces exactly one breach in the next cycle.
- [ ] The audit log records the breach with the input, the threshold, and the time.

---

## 1.5 — Reasoning round-trip via Anthropic SDK

**Goal:** the agent can take a synthesized "protocol state" payload and get a structured decision back.

**Steps:** _TODO when `napg.reasoning` lands._

**Expected:**
- [ ] Decision JSON validates against the schema.
- [ ] Audit log includes the prompt cache hit-rate header from Anthropic.
- [ ] No raw API key appears anywhere in the audit row.

---

## 1.6 — Simulated sequencer-delay end-to-end

**Goal:** the headline Phase 1 milestone — agent detects a simulated sequencer delay and migrates testnet funds.

**Steps:** _TODO when the migration path is implemented._

**Expected:**
- [ ] Migration tx hash appears in audit log and on Base Sepolia explorer.
- [ ] Funds move from monitored address to the safe contract address.
- [ ] Audit log contains a human-readable explanation of why.

---

## 1.7 — Audit log integrity

**Goal:** HMAC tamper-evidence works.

**Steps:**
```bash
# TODO once schema is final:
# sqlite3 audit.db "UPDATE decisions SET inputs='tampered' WHERE id=1"
# uv run python -m napg.audit verify
```

**Expected:**
- [ ] Verify command flags row 1 as tampered and exits non-zero.

---

## 1.8 — Dashboard renders live data

**Goal:** the Next.js dashboard shows real Sepolia data from the agent's FastAPI endpoint.

**Steps:** _TODO when dashboard + API are wired._

**Expected:**
- [ ] Page renders monitor cards for Aerodrome USDC/USDbC and the three Seamless markets.
- [ ] Numbers update on refresh.
- [ ] Devtools console shows no errors; no CORS warnings.

---

## Sign-off checklist

- [ ] All procedures completed.
- [ ] Security checklist for Phase 1 in [PLAN.md](../../PLAN.md#security) reviewed and ticked.
- [ ] Troubleshooting section in [PLAN.md](../../PLAN.md#troubleshooting) reviewed; no items unresolved.
- [ ] User has signed off.
