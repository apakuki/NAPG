# Manual test procedures — Phase 3 (Frontend and Social Distribution)

Status: **skeleton.** Procedures fill in as the dashboard, SIWF, and Base App distribution land. Source-of-truth: [PLAN.md Phase 3](../../PLAN.md#phase-3-wk-4-frontend-and-social-distribution).

Prerequisites: Phase 2 signed off. A test Farcaster account. A Base App build (or in-app browser) for mini-app verification. A staging deployment URL.

---

## 3.1 — SIWF login round-trip

**Goal:** a Farcaster account can sign in and reach the dashboard.

**Steps:** _TODO when SIWF lands._

**Expected:**
- [ ] Sign-in completes; session cookie is `HttpOnly`, `Secure`, `SameSite=Lax`.
- [ ] Dashboard shows the user's Basename (or truncated address fallback).
- [ ] Logout clears the session cookie.

---

## 3.2 — Server-side signature verification

**Goal:** the server actually verifies the SIWF signature; client claims are not trusted.

**Steps:**
```bash
# TODO: use curl or a small script to send a forged login payload.
```

**Expected:**
- [ ] Forged payload is rejected with 401; no session created.

---

## 3.3 — Cookie and CSP audit in devtools

**Goal:** browser-level security headers are correct.

**Steps:**
1. Open the deployed app in Chrome.
2. Devtools -> Application -> Cookies -> verify session cookie flags.
3. Devtools -> Network -> select the document -> Headers -> check `Content-Security-Policy`.

**Expected:**
- [ ] Session cookie has `HttpOnly`, `Secure`, `SameSite=Lax`.
- [ ] CSP has no `unsafe-inline` (or uses a nonce).
- [ ] No NAPG cookie set with `Domain=.com` or similarly broad.

---

## 3.4 — Passkey-backed wallet creation

**Goal:** new user gets a Passkey-backed MPC wallet; no seed phrase is ever shown.

**Steps:** _TODO when CDP MPC + Passkey integration lands._

**Expected:**
- [ ] Passkey prompt fires on wallet creation.
- [ ] No mnemonic, no "back up your seed phrase" UI anywhere.
- [ ] Wallet address resolves and can receive testnet ETH.

---

## 3.5 — EIP-5792 batch with sponsored gas

**Goal:** a multi-op batch executes atomically with paymaster-sponsored gas.

**Steps:** _TODO when batching lands._

**Expected:**
- [ ] Two-op batch lands on one tx hash.
- [ ] User's wallet balance does not change (gas sponsored).

---

## 3.6 — Lighthouse and ZAP

**Goal:** Lighthouse perf/security pass and OWASP ZAP baseline scan come back clean.

**Steps:**
```bash
# Lighthouse:
npx lighthouse https://staging-url --view --preset=mobile
# ZAP baseline (Docker required):
docker run -t zaproxy/zap-stable zap-baseline.py -t https://staging-url
```

**Expected:**
- [ ] Lighthouse Performance >=80, Best Practices and SEO >=90.
- [ ] ZAP baseline reports no HIGH or CRITICAL findings.

---

## 3.7 — Inside the Base App in-app browser

**Goal:** the app actually works in the Base App, not just standalone.

**Steps:** _TODO once submitted to the Base App mini-app directory._

**Expected:**
- [ ] App loads from the Base App mini-app directory.
- [ ] Sign-in works; cookie persists across navigation within the in-app browser.
- [ ] Share-to-Farcaster from a Protocol Health Report opens the compose sheet correctly.

---

## Sign-off checklist

- [ ] All procedures completed.
- [ ] Security and Troubleshooting sections in [PLAN.md](../../PLAN.md) reviewed.
- [ ] User has signed off.
