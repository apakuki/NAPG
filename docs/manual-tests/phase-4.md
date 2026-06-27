# Manual test procedures — Phase 4 (Monetization and Attribution)

Status: **drafted (pre-implementation).** Procedures are written against the
interfaces the [PLAN.md Phase 4](../../PLAN.md#phase-4-wk-5-monetization-and-attribution)
substeps define; commands marked _(provisional)_ finalise when the substep lands.
Source-of-truth for behaviour is PLAN.md; this file is the operator's runbook.

Prerequisites:

- Phase 3 signed off.
- Builder Code registered on Base.dev (the registered code/suffix to hand).
- The agent reachable (`cd agent && uv run napg serve`) or the staging URL.
- A second wallet or client agent able to make USDC payments on Base Sepolia.
- The reporting public key published (with its `kid`) so report signatures can be
  verified independently.

Convention: `$URL` is the agent/staging base (e.g.
`https://napg-frontend-staging.fly.dev` or `http://127.0.0.1:8000`).

---

## Group C — Builder Code attribution

### 4.1 — Builder Code suffix on every NAPG-originated tx

**Goal:** every NAPG-originated tx carries the registered ERC-8021 Builder Code
suffix in calldata, injected only by the single helper.

**Procedure**
```bash
# Pull the most recent on-chain action rows from the audit log, take their tx
# hashes, and inspect calldata on the Base Sepolia explorer / RPC.  (provisional:
# uses the action query surface + the audit log.)
curl -sS "$URL/api/audit/actions?limit=10" | jq -r '.items[].payload.tx_hash'
# For each hash, fetch the tx and read the trailing calldata bytes:
#   cast tx <hash> input --rpc-url "$BASE_SEPOLIA_RPC_URL"
```

**Expected**
- [ ] All sampled on-chain txs end with the registered Builder Code suffix.
- [ ] The suffix bytes match the code registered on Base.dev exactly.
- [ ] No outlier tx (manual run, test script) bypasses the suffix.

---

### 4.2 — Suffix is helper-only; Stage 2 permits only the suffix

**Goal:** the attribution suffix is the *only* non-empty calldata AgentShield
Stage 2 will pass on a native transfer; arbitrary calldata still fails closed.
This is the Group C security seam.

**Procedure**
```bash
# CI invariant: only napg.attribution constructs the suffix.
grep -rn "builder" agent/napg --include=*.py | grep -iv "napg/attribution" | grep -i suffix
# Expect: no hits outside napg/attribution (mirrors the CI grep test).

# Stage 2 behaviour (provisional CLI, analogous to `napg simulate`):
#  a) native transfer + valid Builder Code suffix  -> Stage 2 PASS
#  b) native transfer + arbitrary 4-byte calldata  -> Stage 2 FAIL (closed)
uv run napg agentshield check --action migrate_to_safe --with-builder-code
uv run napg agentshield check --action migrate_to_safe --calldata 0xdeadbeef
```

**Expected**
- [ ] The grep finds no suffix construction outside `napg.attribution`.
- [ ] (a) passes Stage 2; the `validation` audit row records the pass.
- [ ] (b) fails closed with a policy reason naming the calldata check; a
      `validation` row records the failure. No signature is requested.

---

## Group A + B — Assurance Report and x402

### 4.3 — x402 negative path (non-paying client)

**Goal:** an unpaid request returns HTTP 402 with payment requirements.

**Procedure**
```bash
curl -i "$URL/api/x402/assurance-report" -H "content-type: application/json" \
  -d '{"protocol":"aerodrome"}'
```

**Expected**
- [ ] Response is `402 Payment Required`.
- [ ] Payment requirements are present (body or `X-402-*` / `WWW-Authenticate`
      style headers): amount, asset (USDC), chain, and pay-to address.
- [ ] No report content is leaked in the 402 body.

---

### 4.4 — x402 happy path (paying client gets a signed report)

**Goal:** a valid payment returns a signed Assurance Report.

**Procedure** _(provisional: uses the client-agent payment helper from Group B.)_
```bash
# Client constructs + signs the EIP-712 x402 payment, then retries with the
# receipt attached:
uv run napg x402-client pay --to "$URL/api/x402/assurance-report" \
  --protocol aerodrome --amount-usdc 0.10 > /tmp/report.json
jq . /tmp/report.json
```

**Expected**
- [ ] Server returns `200` with the Assurance Report payload
      (`protocol`, `window`, `breaches[]`, `recommendation`, `generated_at`,
      `kid`, `signature`).
- [ ] The `breaches[]` reconcile with the audit log for the same window.
- [ ] A `report` row and a payment row are written to the append-only audit log.

---

### 4.5 — Report signature verification and tamper rejection

**Goal:** an unmodified report verifies against the published reporting public
key; a tampered one fails.

**Procedure**
```bash
# Verify as published:
uv run napg report verify --in /tmp/report.json --pubkey "$REPORTING_PUBKEY"
# Flip a byte in the recommendation, re-verify:
jq '.recommendation = "TAMPERED"' /tmp/report.json > /tmp/report_bad.json
uv run napg report verify --in /tmp/report_bad.json --pubkey "$REPORTING_PUBKEY"
```

**Expected**
- [ ] The unmodified report verifies (exit 0).
- [ ] The tampered report fails verification (non-zero) and names the mismatch.
- [ ] The signature carries a `kid` that matches the published key.

---

### 4.6 — Replay protection (nonce + expiry)

**Goal:** re-sending an already-used payment receipt is rejected.

**Procedure** _(provisional: replay the receipt captured in 4.4.)_
```bash
uv run napg x402-client replay --to "$URL/api/x402/assurance-report" \
  --receipt /tmp/last-receipt.json
# Also test an expired receipt (past its expiry timestamp).
```

**Expected**
- [ ] The replayed receipt is rejected (4xx) and produces no second report.
- [ ] An expired receipt is rejected even on first use.
- [ ] The rejection is recorded in the audit log; the nonce store shows the
      original spend.

---

### 4.7 — Idempotency (one payment = one report)

**Goal:** a duplicate request for the same payment returns the original report,
never a second one.

**Procedure**
```bash
# Re-issue the same request with the same idempotency key as 4.4:
uv run napg x402-client pay --to "$URL/api/x402/assurance-report" \
  --protocol aerodrome --amount-usdc 0.10 --idempotency-key "$KEY" > /tmp/report2.json
diff <(jq -S . /tmp/report.json) <(jq -S . /tmp/report2.json)
```

**Expected**
- [ ] The second response is byte-identical to the first (same signature, same
      `generated_at`).
- [ ] Exactly one `report` row exists in the audit log for that idempotency key.

---

### 4.8 — Reporting key separation

**Goal:** the reporting key is distinct from the operational MPC wallet key.

**Procedure**
```bash
# The report signer address must differ from the agent's operational address.
jq -r '.kid' /tmp/report.json
# Compare the recovered signer / published reporting address against the agent
# wallet address used by migrate_to_safe.
```

**Expected**
- [ ] The reporting signer address != the operational wallet address.
- [ ] The reporting private key never appears in the audit DB, logs (`***`), or
      any API response.
- [ ] Rotating the reporting key changes the `kid`; old reports still verify
      against the old published key.

---

## Group D — Guardian Mode

### 4.9 — Entitlement check is audit-DB-backed, not client-claimed

**Goal:** Guardian Mode access is decided from the audit DB, never from a value
the client supplies.

**Procedure** _(provisional: entitlement surface from Group D.)_
```bash
# Without an entitlement record:
curl -sS "$URL/api/guardian/status?fid=12345"
# Forge a client-side entitlement claim and confirm it is ignored:
curl -sS "$URL/api/guardian/status?fid=12345" -H "x-entitled: true"
# Insert a real entitlement (via the payment path), then re-check.
```

**Expected**
- [ ] No-record fid reads as not entitled.
- [ ] A forged client claim does not grant entitlement.
- [ ] After a real entitlement lands in the audit DB, the same fid reads as
      entitled.

---

## Group E — MEV gate for token actions

### 4.10 — Stage 2 mandatory slippage floor (fail-closed)

**Goal:** a swap intent with no `min_out_wei`, or exceeding `max_slippage_bps`,
is unsignable.

**Procedure** _(provisional swap-intent CLI, analogous to `napg simulate`.)_
```bash
# a) swap with no min_out_wei:
uv run napg agentshield check --action swap --quoted-out 1000000 --min-out ""
# b) swap whose min_out implies slippage beyond the cap:
uv run napg agentshield check --action swap --quoted-out 1000000 --min-out 800000
# c) swap with min_out within the cap:
uv run napg agentshield check --action swap --quoted-out 1000000 --min-out 998000
```

**Expected**
- [ ] (a) fails closed: a swap with no slippage floor is rejected at Stage 2.
- [ ] (b) fails closed: implied slippage exceeds `max_slippage_bps`
      (`config/policy.toml`).
- [ ] (c) passes Stage 2.
- [ ] Each outcome writes a `validation` row; no signature is requested on (a)/(b).

---

### 4.11 — Stage 3 execution-quality state-diff

**Goal:** Stage 3 rejects a swap whose *simulated* received amount is below
`min_out_wei`, even if the quote looked fine.

**Procedure** _(provisional: drive Tenderly against a route that under-fills.)_
```bash
# Simulate a swap whose realized output in the state diff is < min_out:
uv run napg agentshield check --action swap --quoted-out 1000000 --min-out 999000 \
  --simulate-out 950000
```

**Expected**
- [ ] Stage 3 fails closed: simulated received (950000) < `min_out_wei` (999000).
- [ ] The failure reason names the simulated-vs-minOut shortfall.
- [ ] No signature is requested; a `validation` row records the Stage 3 failure.

---

### 4.12 — Protected submission path for swaps only

**Goal:** swaps submit through the MEV-protected endpoint; native transfers keep
using the default RPC.

**Procedure**
```bash
# Inspect the configured protected endpoint:
grep -i "protected\|mev\|submission" agent/napg/config.py
# Execute a dry-run swap and a dry-run migrate; confirm the submission target.
uv run napg simulate swap --dry-run -v        # provisional
uv run napg simulate sequencer-delay --dry-run -v
```

**Expected**
- [ ] The swap path routes to the configured MEV-protected endpoint.
- [ ] The native-transfer (`migrate_to_safe`) path is unchanged (default RPC).
- [ ] Submission happens only after `validate_or_die` passes (CI invariant: no
      signing outside `napg.actions` / `napg.agentshield`).
- [ ] If the protected endpoint is down, the circuit-breaker behaves per
      `monitor/resilience.py` (no silent fallback to an unprotected path).

---

### 4.13 — Realized slippage surfaces as a breach

**Goal:** MEV / adverse execution shows up as a `realized_slippage_bps_max`
breach in the audit log and dashboard.

**Procedure** _(provisional: run the post-trade probe against a known under-fill.)_
```bash
uv run napg simulate swap --realized-out 950000 --quoted-out 1000000
curl -sS "$URL/api/audit/breaches?source=swap&limit=5" | jq '.items[].payload.rule'
```

**Expected**
- [ ] A `realized_slippage_bps_max` breach row is written when realized slippage
      exceeds the threshold in `config/breaches.toml`.
- [ ] The breach renders on `/breaches` and the per-protocol detail page.
- [ ] The breach reconciles into any Assurance Report covering that window.

---

## Group B (accounting)

### 4.14 — Revenue reconciliation

**Goal:** the audit DB's revenue records match onchain USDC receipts for a test
billing period.

**Procedure** _(provisional: reconciliation script from Group B.)_
```bash
uv run napg revenue reconcile --from-block <N> --to-block <M>
```

**Expected**
- [ ] Audit-DB payment totals match onchain USDC receipts to the unit (no
      rounding drift).
- [ ] Every payment row maps to exactly one onchain receipt and vice versa.
- [ ] Any drift is traced to a root cause (missed event, pagination off-by-one),
      never papered over.

---

## Sign-off checklist

- [ ] Procedures 4.1–4.14 completed.
- [ ] CI grep test for the Builder Code helper is green; Stage 2 permits only the
      suffix (4.2).
- [ ] No swap is signable without a slippage floor (4.10) and Stage 3 blocks an
      under-minOut fill (4.11).
- [ ] Reporting key confirmed separate from the operational key (4.8).
- [ ] Phase 4 threat-model addendum filed (x402 payment surface, reporting-key
      compromise, Builder-Code calldata injection, MEV / adverse-execution).
- [ ] Security and Troubleshooting sections in [PLAN.md](../../PLAN.md) reviewed.
- [ ] User signs off in chat with name + date.
