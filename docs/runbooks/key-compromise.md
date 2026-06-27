# Runbook: key compromise

Status: **playbook drafted; some steps need an operator decision (marked
DECISION).** Covers what to do if any signing-control material leaks. Written
2026-06-28 in response to an external review gap (no recovery path documented).

NAPG holds several distinct secrets, each with a different blast radius. They are
deliberately separate so one leak does not imply the others:

| Material | What it controls | Where it lives | Worst case if leaked |
|---|---|---|---|
| `CDP_WALLET_SECRET` (+ API key id/secret) | Server-side signing authority over the MPC operational wallet | `fly secrets` / `.env` (never the audit DB) | An attacker can request signatures from the agent's wallet |
| `NAPG_REPORTING_SIGNING_KEY` | Signs Assurance Reports (Ed25519 seed) | `fly secrets` / `.env` | Forged reports verify against the published `kid` |
| `NAPG_AUDIT_HMAC_KEY` | Tamper-evidence on the audit log | `fly secrets` / `.env` | Attacker can re-sign tampered audit rows |

The private keys themselves never enter agent code (MPC keys live in CDP's TEE);
the items above are the *control* material. None is ever written to the audit DB
(enforced by `test_audit_row_never_contains_the_api_key` and the reporting-seed
leak test).

---

## 0. First move, always: engage the kill switch

Before diagnosing anything, halt signing. See
[kill-switch.md](kill-switch.md). This stops the agent from initiating any new
signature while you contain. It does **not** recall in-flight transactions (see
the transaction-state section of that runbook).

```bash
fly secrets set -a napg-agent-staging NAPG_KILL_SWITCH=1   # prod app name in prod
```

---

## 1. CDP operational wallet key compromise (highest severity)

The attacker can ask the agent's wallet to sign. The dust caps in
`config/policy.toml` (per-tx + daily) bound the loss *if* AgentShield is in the
path, but assume the attacker can bypass the agent process entirely with the
leaked secret. Treat all wallet funds as at risk.

1. **Kill switch on** (section 0).
2. **Drain to the safe address.** While you still control the wallet, move funds
   to the pre-pinned `NAPG_SAFE_CONTRACT_ADDRESS` — this is exactly what
   `migrate_to_safe` does. DECISION: if AgentShield itself is degraded (e.g.
   Tenderly down), use the controlled-override path in
   [infra-outage.md](infra-outage.md) rather than leaving funds exposed.
3. **Rotate the CDP credentials.** Generate a fresh API key + wallet secret in
   the [CDP portal](https://portal.cdp.coinbase.com/), provision a new wallet,
   update `fly secrets`. The old wallet is now abandoned; never reuse it.
4. **Revoke the leaked API key** in the CDP portal so it cannot sign even if the
   kill switch is later lifted.
5. Re-point `CDP_AGENT_ADDRESS` / safe config at the new wallet; redeploy.
6. Post-mortem (section 4).

## 2. Reporting key compromise

The attacker can forge Assurance Reports that verify against the currently
published `kid`. No funds are at risk, but downstream consumers (x402 buyers,
Guardian subscribers) may trust forged reports.

1. **Rotate the reporting key**: `napg report generate-key` produces a new seed +
   public key with a *new* `kid`. Set `NAPG_REPORTING_SIGNING_KEY` to the new
   seed; publish the new public key.
2. **Invalidate the compromised `kid`**: publish a revocation note listing the
   bad `kid` and the rotation timestamp. Reports signed with the old `kid` after
   that timestamp must be treated as forgeries. (Reports legitimately issued
   *before* the leak still verify against the old published key — keep it
   published, marked revoked-as-of-T.)
3. DECISION: whether to re-issue affected reports. For paid x402 reports, the
   audit `payment` + `report` rows let you identify and re-sign genuine ones.

## 3. Audit HMAC key compromise

The log's append-only SQLite triggers still block UPDATE/DELETE; the HMAC is the
second layer. A leaked HMAC key lets an attacker who *also* bypasses the triggers
re-sign tampered rows.

1. Rotate `NAPG_AUDIT_HMAC_KEY`. Note: rows written under the old key will no
   longer verify under the new one — `napg audit verify` will flag them. This is
   expected; record the rotation timestamp so verification is interpreted
   against the right key epoch (full multi-epoch verification is a Phase 5 item).
2. Take an integrity snapshot (`napg audit verify` + a copy of the DB) *before*
   rotating so you have a known-state baseline.

---

## 4. Always: post-incident

- Record the timeline in the audit log and the incident channel.
- Confirm the leaked material is dead (revoked + rotated, not just rotated).
- Check backups and any out-of-repo copies still holding the dead secret (see
  the CDP-key-leak precedent: a scrubbed-from-history key still lived in
  backups).
- File a written post-mortem: how it leaked, blast radius, what changed.

## Open decisions (need operator sign-off before mainnet)

- The drain-to-safe step when AgentShield is itself degraded — depends on the
  [infra-outage.md](infra-outage.md) Tenderly decision.
- Whether key rotation requires multi-party authority (see
  [kill-switch.md](kill-switch.md) governance section).
