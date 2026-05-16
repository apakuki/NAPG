# Manual test procedures — Phase 5 (Mainnet launch)

Status: **skeleton.** Procedures fill in during the mainnet cutover. Source-of-truth: [PLAN.md Phase 5](../../PLAN.md#phase-5-wk-6-mainnet-launch).

Prerequisites: Phases 0-4 signed off. Fly.io app provisioned, secrets loaded, persistent volume mounted. Mainnet RPC and CDP wallet configured with tight caps. Reporting key rotated for production.

---

## 5.1 — Fly deploy lands cleanly

**Goal:** the production deploy comes up healthy.

**Steps:**
```bash
fly deploy
fly status
fly logs
```

**Expected:**
- [ ] Status reports a healthy machine.
- [ ] Logs show monitoring loop starting against Base mainnet.
- [ ] `/healthz` returns 200 within 30 seconds of boot.

---

## 5.2 — Secrets are in `fly secrets`, not in the image

**Goal:** no secret material baked into the Docker image.

**Steps:**
```bash
fly ssh console -C "env | grep -iE 'KEY|SECRET|TOKEN' | wc -l"
docker history $(fly status --json | jq -r .ImageRef) | grep -iE 'KEY|SECRET' || echo "clean image"
```

**Expected:**
- [ ] Env count matches the expected secrets list (sourced from `fly secrets list`).
- [ ] Image history shows "clean image".

---

## 5.3 — Audit DB encryption at rest

**Goal:** the audit DB sits on an encrypted Fly volume.

**Steps:**
```bash
fly volumes list
```

**Expected:**
- [ ] Volume hosting the audit DB reports `encrypted: true` (or equivalent).

---

## 5.4 — Backup and restore drill

**Goal:** a full restore from yesterday's backup produces a working agent state.

**Steps:** _TODO once backup script lands._

**Expected:**
- [ ] Restored DB matches the source by row count and HMAC verification.
- [ ] Agent boots against the restored DB without integrity errors.

---

## 5.5 — Kill-switch drill on mainnet

**Goal:** the kill-switch works in production exactly as it did in staging.

**Steps:** _TODO once the production switch mechanism is defined._

**Expected:**
- [ ] Switch engaged; the next signing attempt is skipped within 1 second.
- [ ] Audit log records the switch event with the engaging principal.

---

## 5.6 — 72-hour unattended run

**Goal:** the agent runs for 72 hours on mainnet with no incidents.

**Steps:**
- Start the agent with mainnet caps set to dust amounts.
- Monitor `fly logs`, the status page, and the audit DB.

**Expected:**
- [ ] No unplanned restarts.
- [ ] No kill-switch engagements.
- [ ] No HIGH/CRITICAL alerts.
- [ ] Memory and disk usage stable.

---

## 5.7 — First Protocol Health Report posted to Farcaster

**Goal:** the cast-driven onboarding loop publishes.

**Steps:**
- Wait for the scheduled job (or trigger manually).
- Verify the cast on Farcaster.

**Expected:**
- [ ] Cast appears with the expected protocol summary.
- [ ] Linked Assurance Report URL resolves.

---

## 5.8 — First external x402 payment

**Goal:** a real external agent (not us) pays for an Assurance Report.

**Steps:**
- Confirm with a partner agent that they're going to try.
- Watch the audit DB and onchain USDC receipts.

**Expected:**
- [ ] Payment confirmed onchain; report delivered.
- [ ] Revenue accounting reflects the payment.

---

## 5.9 — Incident response tabletop

**Goal:** the on-call runbook actually works under pressure.

**Steps:**
- Simulate a "false-positive migration" alert in a controlled session.
- Walk through the runbook from page to resolution.

**Expected:**
- [ ] Paging contact responds within agreed SLA.
- [ ] Kill-switch engaged correctly.
- [ ] Comms template used; status page updated.
- [ ] Post-mortem template filled in within 48 hours.

---

## Sign-off checklist

- [ ] All procedures completed.
- [ ] Security and Troubleshooting sections in [PLAN.md](../../PLAN.md) reviewed.
- [ ] Post-launch retrospective scheduled.
- [ ] User has signed off on launch.
