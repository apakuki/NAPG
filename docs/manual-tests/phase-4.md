# Manual test procedures — Phase 4 (Monetization and Attribution)

Status: **skeleton.** Procedures fill in as Builder Code, x402, and Guardian Mode land. Source-of-truth: [PLAN.md Phase 4](../../PLAN.md#phase-4-wk-5-monetization-and-attribution).

Prerequisites: Phase 3 signed off. Builder Code registered on Base.dev. A second wallet (or client agent) able to make USDC payments on Base Sepolia.

---

## 4.1 — Builder Code suffix on every NAPG tx

**Goal:** every NAPG-originated tx carries the registered Builder Code suffix in calldata.

**Steps:**
```bash
# TODO once attribution helper lands:
# Take the last 10 NAPG tx hashes from the audit log; pull calldata from Base Sepolia explorer;
# confirm the suffix is present and matches the registered code.
```

**Expected:**
- [ ] All 10 sampled txs carry the suffix.
- [ ] No outlier txs (manual or test scripts) bypass the helper.

---

## 4.2 — x402 happy path (paying client)

**Goal:** a paying client agent gets a signed Assurance Report.

**Steps:** _TODO when x402 endpoint lands._

**Expected:**
- [ ] Client sends a signed EIP-712 payment receipt; server returns the Assurance Report payload.
- [ ] Report signature verifies against the published reporting public key.

---

## 4.3 — x402 negative path (non-paying client)

**Goal:** the unpaid request gets HTTP 402.

**Steps:**
```bash
curl -i https://staging-url/api/x402/report -d '{"protocol":"aerodrome"}'
```

**Expected:**
- [ ] Response is `402 Payment Required` with payment instructions in the body or `X-402-*` headers.

---

## 4.4 — Replay protection

**Goal:** re-sending an already-used payment receipt is rejected.

**Steps:** _TODO once nonce/expiry are in._

**Expected:**
- [ ] Second request with the same receipt returns an error (4xx) and does not produce a second report.

---

## 4.5 — Signature tamper rejection

**Goal:** flipping a byte in the report signature causes verification to fail at the consumer.

**Steps:** _TODO with a small verify-script._

**Expected:**
- [ ] Tampered report fails verification; unmodified report verifies.

---

## 4.6 — Revenue reconciliation

**Goal:** the audit DB's revenue table matches onchain USDC receipts for a test billing period.

**Steps:** _TODO once reconciliation script lands._

**Expected:**
- [ ] Audit-DB totals match onchain totals to the unit (no rounding drift).
- [ ] Any drift is investigated to root cause, not papered over.

---

## Sign-off checklist

- [ ] All procedures completed.
- [ ] Security and Troubleshooting sections in [PLAN.md](../../PLAN.md) reviewed.
- [ ] User has signed off.
