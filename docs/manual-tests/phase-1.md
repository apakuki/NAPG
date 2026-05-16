# Manual test procedures — Phase 1 (Prototype and Logic Core)

Status: **skeleton.** Procedures fill in as monitors, reasoning, and migration land. Source-of-truth for what's being built: [PLAN.md Phase 1](../../PLAN.md#phase-1-wk-1-2-prototype-and-logic-core).

Prerequisites (once Phase 1 starts): `.env` filled in with `ANTHROPIC_API_KEY`, `BASE_SEPOLIA_RPC_URL`, `CDP_*` testnet wallet, `ZEROX_API_KEY`, `TENDERLY_*`. Testnet ETH in the agent wallet.

---

## 1.1 — RPC heartbeat against Base Sepolia

**Goal:** confirm Web3.py is hitting Base Sepolia and reporting latency, block height, and reorg state.

**Steps:** _TODO when `napg.monitor.rpc` lands._

**Expected:**
- [ ] Block height advances within ~2 seconds of head.
- [ ] Reported latency under threshold defined in `config/breaches.toml`.
- [ ] Reorg counter remains at 0 during a quiet window.

---

## 1.2 — Aerodrome USDC/USDbC pool probe

**Goal:** liquidity and pool-state numbers match a manual check on a block explorer.

**Steps:** _TODO when `napg.monitor.aerodrome` lands._

**Expected:**
- [ ] Reserve numbers within 1% of explorer-reported figures.
- [ ] Peg-deviation metric reads near zero when the pool is healthy.

---

## 1.3 — Seamless market state (USDC, WETH, cbETH)

**Goal:** utilization, oracle freshness, and supply caps match Seamless's own dashboard.

**Steps:** _TODO when `napg.monitor.seamless` lands._

**Expected:**
- [ ] All three markets report current utilization to within 0.5% of Seamless UI.
- [ ] Oracle age in seconds is within the expected refresh interval.

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
