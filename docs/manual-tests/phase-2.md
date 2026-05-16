# Manual test procedures — Phase 2 (Security Layer / AgentShield)

Status: **skeleton.** Procedures fill in as the 4-stage pipeline lands. Source-of-truth: [PLAN.md Phase 2](../../PLAN.md#phase-2-wk-3-security-layer).

Prerequisites: Phase 1 signed off. `.env` with Tenderly access key. Known-honeypot token address on Base Sepolia for negative testing.

---

## 2.1 — Stage 1 (Intent Judge) blocks an off-goal action

**Goal:** the Intent Judge refuses a tx whose intent doesn't match the agent's current goal.

**Steps:** _TODO when `napg.shield.intent` lands._

**Expected:**
- [ ] A tx labelled "rescue migration" but actually swapping unrelated tokens is rejected at Stage 1.
- [ ] Audit log records the rejection with the Judge's reasoning.

---

## 2.2 — Stage 2 (Policy) blocks a denylisted destination

**Goal:** a tx targeting a denylisted address is rejected before simulation.

**Steps:** _TODO when `napg.shield.policy` lands._

**Expected:**
- [ ] Tx targeting a denylisted address fails policy and is audit-logged.
- [ ] No Tenderly call is made (stage ordering preserved).

---

## 2.3 — Stage 3 (Tenderly) catches an unexpected balance change

**Goal:** a tx that would unexpectedly transfer the agent's full balance fails at simulation.

**Steps:** _TODO when `napg.shield.simulate` lands._

**Expected:**
- [ ] Simulation returns a state diff; the analyzer flags the unexpected balance change.
- [ ] Tx is rejected before signing.

---

## 2.4 — Stage 4 (Honeypot) rejects a known honeypot

**Goal:** the BUY-then-SELL probe correctly fails on a known-bad token.

**Steps:** _TODO when `napg.shield.honeypot` lands._

**Expected:**
- [ ] Probe BUY simulation succeeds; SELL simulation reverts or returns unexpected balance.
- [ ] Honeypot result is cached, keyed by the token's `codeHash`.

---

## 2.5 — `validate_or_die` is the only signing entry point

**Goal:** confirm no code path bypasses the gate.

**Steps:**
```bash
# CI lint should already enforce this; this is a manual cross-check.
rg -n "wallet\.(sign|send|invoke)" agent/napg/
```

**Expected:**
- [ ] Only matches inside `agent/napg/shield/validate.py` (or wherever `validate_or_die` lives).
- [ ] Every other module that needs to sign goes through the gate.

---

## 2.6 — Kill-switch drill

**Goal:** engaging the kill-switch halts the next signing attempt.

**Steps:** _TODO when kill-switch lands._

**Expected:**
- [ ] Switch engaged; the very next decision cycle skips signing and audit-logs "kill-switch active".
- [ ] Switch propagation under 1 second on a single-instance deployment.

---

## 2.7 — Policy config signature enforcement

**Goal:** the loader refuses an unsigned or tampered policy config.

**Steps:**
```bash
# TODO: copy policy.toml, modify a value without re-signing, restart agent.
```

**Expected:**
- [ ] Agent refuses to start; logs "policy config signature mismatch".
- [ ] Restarting with a properly signed config works.

---

## Sign-off checklist

- [ ] All procedures completed.
- [ ] Phase 2 threat-model review filed.
- [ ] Security and Troubleshooting sections in [PLAN.md](../../PLAN.md) reviewed.
- [ ] User has signed off.
