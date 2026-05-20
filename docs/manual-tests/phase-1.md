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

**Goal:** flipping a single threshold below the current observed state produces exactly one matching breach record; default thresholds leave a healthy run green.

The rules engine lands in `napg.policy.breaches`. The full end-to-end demo (run probes → evaluate → write to audit log) lands with substep 9; this test exercises the evaluator in isolation against the live probe outputs.

**Steps:**
```bash
# From agent/. Captures a real heartbeat, runs it through the default
# thresholds, then through a tightened threshold to force a breach.
uv run python - <<'PY'
from napg.config import Settings
from napg.monitor.rpc import RpcHeartbeat
from napg.policy.breaches import BreachThresholds, evaluate

heart = RpcHeartbeat(Settings().active_rpc_url())
beat = heart.tick()

# Default thresholds — expect no breaches against a healthy heartbeat.
print("default:", evaluate(BreachThresholds(), heartbeat=beat))

# Tighten latency below the observed value.
tight = BreachThresholds(rpc_latency_ms_max=max(0, int(beat.latency_ms) - 1))
print("tight:", evaluate(tight, heartbeat=beat))
PY
```

**Expected:**
- [x] `default:` line prints `()` — every default threshold is wide enough that a healthy heartbeat is green.
- [x] `tight:` line prints a one-element tuple containing a `Breach` with `rule='rpc_latency_ms_max'`, `source='heartbeat'`, an `actual` value matching the observed latency, and the lowered `threshold`.
- [x] The breach record's `message` includes both the actual and threshold values.

Verified 2026-05-19 against live Base Sepolia heartbeat: 883ms observed → default thresholds returned `()`, threshold tightened to 882ms returned a single `Breach` matching the contract exactly.

---

## 1.5 — Reasoning round-trip via Anthropic SDK

**Goal:** the agent can take a synthesized "protocol state" payload, call Claude Opus, and get a structured decision back; the audit log captures cache metadata; the API key does not leak.

**Prerequisites:** `.env` with both `ANTHROPIC_API_KEY` and `NAPG_AUDIT_HMAC_KEY` populated. **This test makes two real Anthropic API calls** (~5 cents at current Opus pricing). The second call demonstrates prompt cache hit by reusing the cached system block.

**Steps:**
```bash
# From agent/. Builds a synthetic protocol-state input with a reorg breach,
# calls the reasoner twice (to demonstrate cache hit on the second pass),
# and verifies the audit log via the napg CLI.
rm -f ./audit.db  # start clean for the demo

uv run python - <<'PY'
from napg.audit import AuditLog
from napg.config import Settings
from napg.monitor.rpc import BlockSnapshot, HeartbeatResult
from napg.policy.breaches import Breach
from napg.reasoning import Reasoner, ReasoningInputs

settings = Settings()
HASH_A = "0x" + "aa" * 32
HASH_B = "0x" + "bb" * 32

heartbeat = HeartbeatResult(
    rpc_url="https://example/<redacted>",
    chain_id=84532,
    latency_ms=120.0,
    block=BlockSnapshot(number=46_200_000, hash=HASH_A, parent_hash=HASH_B,
                       timestamp=1779170000),
    reorg_detected=True,
    observed_at=1779170001.0,
)
breaches = (Breach(rule="reorg_is_breach", source="heartbeat",
                   threshold=False, actual=True,
                   message="RPC heartbeat reported a chain reorganisation",
                   detected_at=1779170001.0),)
inputs = ReasoningInputs(heartbeat=heartbeat, breaches=breaches)

with AuditLog(settings.audit_db_path, hmac_key=settings.audit_hmac_key) as log:
    reasoner = Reasoner(api_key=settings.anthropic_api_key, audit_log=log)

    cold = reasoner.decide(inputs)
    print("cold:", cold.intent, "cache_creation=",
          cold.cache_metadata.cache_creation_input_tokens,
          "cache_read=", cold.cache_metadata.cache_read_input_tokens)

    warm = reasoner.decide(inputs)
    print("warm:", warm.intent, "cache_creation=",
          warm.cache_metadata.cache_creation_input_tokens,
          "cache_read=", warm.cache_metadata.cache_read_input_tokens)
PY

uv run python -m napg audit verify
```

**Expected:**
- [x] Both `cold:` and `warm:` lines print one of the intents in the schema (`hold` / `migrate_to_safe` / `pause_for_investigation`).
- [x] On the cold call, `cache_creation_input_tokens` is non-zero and `cache_read_input_tokens` is 0.
- [x] On the warm call, `cache_read_input_tokens` is non-zero and matches the cold call's `cache_creation_input_tokens` exactly (proves the cached prefix was reused).
- [x] `napg audit verify` reports `total_rows: 2`, `tampered: []`, exit code 0.
- [x] `grep -a "$ANTHROPIC_API_KEY" ./audit.db` finds nothing (the API key never lands in the DB).

Verified 2026-05-19 against live Claude Opus 4.7 with the substep-5 expanded system prompt:
- Cold call: input_tokens=1007, cache_creation=2406, cache_read=0, output_tokens=240, intent=`migrate_to_safe`, rationale cited `reorg_is_breach` and decision-matrix rule 2 by name.
- Warm call: input_tokens=26, cache_read=2406 (exact match of cold's cache_creation), cache_creation=981 (Anthropic's auto-caching extends the prefix on repeat content), output_tokens=259, intent=`migrate_to_safe`.
- `napg audit verify` returned `{"total_rows": 2, "tampered": []}` and exit 0.
- Both decision rows passed HMAC verification; the API key is excluded from audit rows by `test_audit_row_never_contains_the_api_key`.

---

## 1.6 — Simulated sequencer-delay end-to-end

**Goal:** the headline Phase 1 milestone — agent detects a simulated sequencer delay and migrates testnet funds.

Substep 6 lands the *action* primitive (`napg.actions.migrate_to_safe`) and the CDP-backed agent wallet (`napg.wallet.build_agent_wallet`). This test exercises the action in isolation, both dry-run and live. The full reasoning → action loop closes in substep 9.

**Prerequisites:**
- `.env` populated with `CDP_API_KEY_NAME`, `CDP_API_KEY_PRIVATE_KEY`, `CDP_WALLET_SECRET` (v2), and `NAPG_AUDIT_HMAC_KEY`
- A funded Base Sepolia agent wallet (created on first run; address recorded in `CDP_AGENT_ADDRESS` for subsequent runs)
- `NAPG_SAFE_CONTRACT_ADDRESS` set to a destination wallet you control (Phase 1: any Sepolia address you own; Phase 5: a vetted safe contract)

**Steps:**
```bash
# 1. Provision (on first run) and display the agent wallet
uv run python -m napg wallet show
# Copy the printed `address` into CDP_AGENT_ADDRESS in .env so subsequent
# runs reuse the same wallet rather than creating fresh accounts.

# 2. Fund the agent wallet from a Base Sepolia faucet
# (Coinbase Faucet, Alchemy Faucet, or any other Sepolia faucet)

# 3. Dry-run the migration — should succeed without sending a tx
uv run python -m napg migrate --amount-eth 0.001

# 4. Execute a real migration — sends a Base Sepolia tx
uv run python -m napg migrate --amount-eth 0.001 --execute

# 5. Verify the audit log captured both calls
uv run python -m napg audit verify
```

**Expected:**
- [ ] `wallet show` prints a `0x`-prefixed agent address, a `balance_wei` value, and `network: base-sepolia`.
- [ ] The dry-run output is an `ActionRecord` with `dry_run=true`, no `tx_hash`, no `block_number`.
- [ ] The `--execute` output is an `ActionRecord` with `dry_run=false`, a real `tx_hash`, a `block_number`, and `status=success`.
- [ ] The tx hash is visible on Base Sepolia explorer (https://sepolia.basescan.org) with the correct from/to/value.
- [ ] `napg audit verify` reports `total_rows: 2`, `tampered: []`, exit code 0.
- [ ] `grep -a "$CDP_WALLET_SECRET" ./audit.db` finds nothing (the wallet secret never lands in the DB).

The "agent detects a simulated sequencer delay and migrates testnet funds" milestone closes in [substep 9](#19--simulated-sequencer-delay-end-to-end-pipeline) once the heartbeat probe → breach evaluator → reasoner → action pipeline is wired end-to-end.

---

## 1.7 — Audit log integrity

**Goal:** demonstrate the two-layer defence — the append-only triggers reject the naive tamper, and after the triggers are dropped the row-level HMAC still detects the change.

**Prerequisites:** `.env` populated with `NAPG_AUDIT_HMAC_KEY` (`python -c "import secrets; print(secrets.token_hex(32))"` for a fresh one). The DB lives at `NAPG_AUDIT_DB` (default `./audit.db`).

**Steps:**
```bash
# From agent/. Writes a couple of breach rows, then probes both defences.
uv run python - <<'PY'
import os
from pathlib import Path

from napg.audit import AuditLog
from napg.config import Settings
from napg.policy.breaches import Breach

settings = Settings()
db = Path(settings.audit_db_path)
db.unlink(missing_ok=True)  # start clean for the demo

with AuditLog(db, hmac_key=settings.audit_hmac_key) as log:
    log.record_breaches([
        Breach(rule="rpc_latency_ms_max", source="heartbeat",
               threshold=2000, actual=3500.0,
               message="RPC latency 3500 ms exceeds threshold 2000 ms",
               detected_at=1716000010.0),
    ])
print("wrote breach to", db)
PY

# Try the naive tamper — expect SQLite to reject it.
sqlite3 ./audit.db "UPDATE audit_log SET payload='tampered' WHERE id=1"

# Drop the triggers, tamper, then verify — verify must detect it.
sqlite3 ./audit.db "DROP TRIGGER audit_log_no_update; UPDATE audit_log SET payload='tampered' WHERE id=1"
uv run python -m napg audit verify
echo "exit code: $?"
```

**Expected:**
- [x] The first `sqlite3 ... UPDATE` exits non-zero with an error containing `audit_log is append-only`.
- [x] After dropping the trigger and tampering, `napg audit verify` prints a JSON report with `total_rows: 1`, `tampered: [1]`, and the process exits with code 1.

Verified 2026-05-19: naive `UPDATE` errored with `audit_log is append-only` (exit 19); after `DROP TRIGGER`, the update succeeded but `napg audit verify` returned `{"total_rows": 1, "tampered": [1]}` and exited with code 1.

---

## 1.8 — Dashboard renders live data

**Goal:** the Next.js dashboard shows real Base data from the agent's FastAPI endpoint, refreshes every 10 s, and degrades per-card when an env key is missing.

**Prerequisites:** `.env` populated with `BASE_SEPOLIA_RPC_URL` (heartbeat), `BASE_RPC_URL` (Morpho mainnet), and `ZEROX_API_KEY` (Aerodrome). The Anthropic/CDP keys are not exercised by this test.

**Steps:**
```bash
# From the repo root, with .env populated.
scripts/start.sh
# Dashboard at http://localhost:3000
# Agent API at http://127.0.0.1:8000/api/status (proxy target)

# In another shell, hit the proxy directly to confirm shape.
curl -s http://localhost:3000/api/status | jq

# Stop both processes.
scripts/stop.sh
```

**Expected:**
- [x] Page renders three monitor cards: RPC heartbeat (latency, block, reorg), Aerodrome USDC/USDT (quoted rate, peg deviation, sources, latency), Morpho Blue (per-market utilisation and staleness for `WETH-USDC` and `cbBTC-USDC`).
- [x] Block numbers advance between consecutive `/api/status` calls roughly in line with Base's ~2 s block time.
- [x] If the agent API isn't running, the proxy returns HTTP 502 with `cannot reach agent at ...` and the dashboard shows the red banner.
- [x] "Updated HH:MM:SS" header advances roughly every 10 s without a manual refresh — `dashboard.spec.ts::auto-poll` proves the proxy is hit >=2× over 11 s.
- [x] Switching tabs away for >10 s and back: a fresh fetch fires on re-focus and the updated timestamp ticks again — `dashboard.spec.ts::tab-visibility` simulates `visibilitychange`, asserts no requests while hidden, and a fresh request on restore.
- [x] If `ZEROX_API_KEY` is unset, only the Aerodrome card shows `ZEROX_API_KEY not set`; the other two render normally — `dashboard.spec.ts::per-card degrade`.
- [x] Devtools console shows no errors; no CORS warnings (the dashboard only hits `localhost:3000/api/status`, never the agent directly) — `dashboard.spec.ts::console` collects `console.error` and `pageerror` over the first render + initial fetch; asserts the array is empty.

Verified 2026-05-20 via `scripts/start.sh` + `curl http://localhost:3000/api/status`:
- Heartbeat returned Base Sepolia chain 84532, block 41,735,849, `reorg_detected: false`, ~700 ms latency from Alchemy. RPC URL redacted to scheme + host only.
- Aerodrome probe quoted USDC/USDT at 0.99951 (5 bps peg deviation), route included `Aerodrome_V3` among 7 sources, liquidity available at Base mainnet block 46,225,319.
- Morpho cards: `WETH-USDC` at 90.39 % utilisation, 36 s staleness, ~$77 M supply / $69 M borrow. `cbBTC-USDC` at 90.39 % utilisation, 18 s staleness, ~$1.35 B supply / $1.22 B borrow — matches the public "$1.4 B+ cbBTC collateral" reporting.
- Two probes 11 s apart: Sepolia head advanced 41,735,849 → 41,735,855 (6 blocks); mainnet head 46,225,319 → 46,225,326 (7 blocks). Both consistent with ~2 s block time.
- `/api/status` via the proxy on `:3000` returned an identical shape to the agent direct on `:8000`. `/api/health` returned `{"status": "ok"}`.
- Auto-poll cadence, tab-visibility behaviour, per-card degrade-on-error, and the devtools console check are covered by `frontend/e2e/dashboard.spec.ts` (Playwright + headless Chromium, 5 specs all passing 2026-05-20).

---

## 1.9 — Simulated sequencer-delay end-to-end pipeline

**Goal:** the Phase 1 milestone, closed. The agent runs one full cycle on a synthesized sequencer-delay scenario — heartbeat → breach evaluator → reasoner → migration — with every step audited.

This procedure wires the substep 9 orchestrator (`napg.orchestrator.run_cycle`) and the substep 9 scenario helper (`napg.scenarios.sequencer_delay_heartbeat`) behind the `napg simulate sequencer-delay` CLI. The synthetic heartbeat carries a 600-second-old block plus a reorg flag, which the rules engine maps to three breaches and the reasoning matrix maps to `migrate_to_safe` (rule 2: reorg).

**Prerequisites:**
- 1.6 prerequisites (CDP wallet provisioned, funded on Base Sepolia, `CDP_AGENT_ADDRESS` recorded, `NAPG_SAFE_CONTRACT_ADDRESS` set to a destination you control).
- `ANTHROPIC_API_KEY` and `NAPG_AUDIT_HMAC_KEY` populated in `.env`.

**Steps:**
```bash
# 1. Dry-run pass — no Sepolia tx, but every audit row lands and HMAC-chains.
uv run python -m napg simulate sequencer-delay --amount-eth 0.001

# 2. Verify the cycle wrote scenario + breach(es) + decision + action rows.
uv run python -m napg audit verify

# 3. Live pass — same scenario, but the migration tx hits Sepolia.
uv run python -m napg simulate sequencer-delay --amount-eth 0.001 --execute

# 4. Verify the live cycle's audit chain.
uv run python -m napg audit verify
```

**Expected:**
- [ ] The dry-run report's `breaches` list contains `reorg_is_breach`, `block_age_seconds_max`, and `rpc_latency_ms_max`.
- [ ] The `decision.intent` is `migrate_to_safe`. `supporting_breaches` cites the reorg.
- [ ] The dry-run `action.dry_run` is `true`, `tx_hash` is `null`, `block_number` is `null`.
- [ ] The first `audit verify` reports `ok: true` and `total_rows: 5` (scenario + 3 breaches + decision + action).
- [ ] The live (`--execute`) `action.dry_run` is `false`, `tx_hash` is a real Sepolia tx, `status: success`.
- [ ] That tx appears on https://sepolia.basescan.org with the agent address as `from` and `NAPG_SAFE_CONTRACT_ADDRESS` as `to`.
- [ ] The second `audit verify` reports `ok: true` and the new total is the dry-run total plus 5 more rows.
- [ ] `grep -a "$ANTHROPIC_API_KEY" ./audit.db` and `grep -a "$CDP_WALLET_SECRET" ./audit.db` find nothing.

The first matching reasoning-matrix rule is rule 2 (reorg). If you set `--no-reorg`, the cycle should instead choose `pause_for_investigation` and no `action` row should appear. That alternate path is exercised by `tests/test_orchestrator.py::test_pause_intent_writes_decision_but_no_action`.

---

## Sign-off checklist

- [ ] All procedures completed.
- [ ] Security checklist for Phase 1 in [PLAN.md](../../PLAN.md#security) reviewed and ticked.
- [ ] Troubleshooting section in [PLAN.md](../../PLAN.md#troubleshooting) reviewed; no items unresolved.
- [ ] User has signed off.
