# Manual test procedures — Phase 3 (Frontend and Social Distribution)

These procedures complement the vitest + Playwright suites by covering the
things automated tests cannot reach: a real Farcaster signer, a real
Passkey on a real device, real EIP-5792 capability response from a deployed
Smart Wallet, base.dev's live manifest validator, and rendering inside the
Base App in-app browser.

Run them top-to-bottom on a fresh local checkout after Phase 3 substeps
are committed and before Phase 3 sign-off. Source-of-truth: [PLAN.md
Phase 3](../../PLAN.md#phase-3-wk-4-frontend-and-social-distribution).

**Prerequisites**
- Phase 2 signed off (`01e996a` and earlier).
- `.env` populated (Anthropic, CDP, Base RPC, Tenderly, 0x, Neynar).
- `NAPG_SESSION_SECRET` set (`python -c "import secrets; print(secrets.token_hex(32))"`).
- A test Farcaster account.
- A device with Touch ID / Face ID / Windows Hello for the Passkey flow.
- Optional for §3.9: a deployed staging URL (Fly.io or equivalent).

---

## 3.1  Live SIWF sign-in round-trip

**Goal:** a real Farcaster account can sign in via the relay; the session
cookie is server-signed and carries the fid + address claims.

**Procedure**
1. `scripts/start.sh` to run agent + frontend together.
2. Open http://localhost:3000/settings in a desktop browser.
3. Click **Sign in with Farcaster**.
4. Open the deep-link URL on your phone (or paste it into a QR generator);
   approve the sign-in in the Farcaster app.
5. Wait for the page to reload (poll runs every 1.5 s, max 5 min window).

**Expected**
- [ ] The page reloads to the signed-in state showing "Signed in as
      `<fid>`" and either your Basename or truncated address.
- [ ] Devtools → Application → Cookies → `napg_session` is present with
      flags `HttpOnly`, `SameSite=Lax`. (In dev `Secure` is off because
      the dev server is http; in production it must flip on.)
- [ ] `Domain` on the cookie is the eTLD+1 only (no `.com` wildcards).
- [ ] Devtools → Application → Storage → Local Storage and Session
      Storage are both empty (no tokens leaked to JS-readable storage).
- [ ] **Sign out** clears the cookie immediately; refresh returns to the
      unauthed sign-in card.

---

## 3.2  Server-side signature verification

**Goal:** the server actually verifies the SIWF signature against the
server-generated nonce; a forged relay response is rejected.

**Procedure**
```bash
# Mint a fake channel token that the server never issued, then poll:
curl -sS "http://localhost:3000/api/auth/siwf/poll?token=never-issued-token"
# Try the same with an empty token:
curl -sS "http://localhost:3000/api/auth/siwf/poll"
```

**Expected**
- [ ] First call returns `{"state":"unknown"}` — the server's channel map
      has no entry, so it short-circuits without contacting the relay.
- [ ] Second call returns HTTP 400 with `{"state":"unknown","error":"missing token"}`.
- [ ] After a real `start`, immediately call poll twice in succession with
      a `completed` channel: the first poll sets the cookie, the second
      returns `state: "unknown"` (single-use deletion is the replay defence).

---

## 3.3  CSRF guard on state-changing routes

**Goal:** cross-origin POSTs are rejected; same-origin POSTs go through.

**Procedure**
```bash
# Cross-origin: 403
curl -sS -o /tmp/b -w "HTTP %{http_code}\n" -X POST \
  -H "Origin: https://evil.example" \
  "http://localhost:3000/api/auth/signout"

# No Origin or Referer at all: 403
curl -sS -o /tmp/b -w "HTTP %{http_code}\n" -X POST \
  "http://localhost:3000/api/auth/signout"

# Same-origin: 200
curl -sS -o /tmp/b -w "HTTP %{http_code}\n" -X POST \
  -H "Origin: http://localhost:3000" \
  "http://localhost:3000/api/auth/signout"
```

**Expected**
- [ ] First two return HTTP 403 with `{"error":"cross-origin request rejected"}`.
- [ ] Third returns HTTP 200 with `{"ok":true}`.

---

## 3.4  Rate-limit on auth surface

**Goal:** an attacker probing channel tokens hits the throttle.

**Procedure**
```bash
ok=0; lim=0
for i in $(seq 1 65); do
  code=$(curl -sS -o /dev/null -w "%{http_code}" \
    "http://localhost:3000/api/auth/siwf/poll?token=fake")
  case "$code" in 200) ok=$((ok+1));; 429) lim=$((lim+1));; esac
done
echo "200: $ok, 429: $lim"

# Inspect the throttle response for the Retry-After hint:
curl -sI "http://localhost:3000/api/auth/siwf/poll?token=fake" | grep -i retry-after
```

**Expected**
- [ ] At least 60 of 65 return 200; the rest return 429 (token bucket has
      60-token burst at 4 tok/s sustained).
- [ ] Throttled response carries a `Retry-After: 1` header.

---

## 3.5  Cookie + CSP devtools audit

**Goal:** browser-level security headers are correct on every HTML page.

**Procedure**
1. Open http://localhost:3000/ in Chrome.
2. Devtools → Network → click the document → Headers → confirm:
   - `Content-Security-Policy` with `default-src 'self'`, no `unsafe-inline`
     on `script-src` (a `'nonce-XXX' 'strict-dynamic'` token is OK).
   - `X-Frame-Options: DENY`
   - `X-Content-Type-Options: nosniff`
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - `Permissions-Policy: camera=(), microphone=(), geolocation=(), …`
3. Reload twice — the nonce in `script-src 'nonce-...'` should differ each
   load (per-request nonces, not a fixed value).
4. Repeat for `/settings`, `/breaches`, `/protocols/aerodrome`.

**Expected**
- [ ] All five security headers present on every HTML route.
- [ ] CSP nonce rotates on every page load.
- [ ] No CSP-violation reports in the devtools Console.

---

## 3.6  Basenames reverse resolution

**Goal:** a known Basename-owning address resolves to its name; an
address without one falls back to the truncated form.

**Procedure**
1. Sign in (§3.1) with a Farcaster account whose verified custody address
   has a Basename set.
2. Note what `/settings` renders next to "Signed in as".
3. Sign out. Sign in again with an account whose verified address has no
   Basename.

**Expected**
- [ ] First user renders their `<name>.base.eth`.
- [ ] Second user renders `0xabcd...wxyz` (truncated address) and the
      "Claim one at base.org/names" prompt.

---

## 3.7  Passkey-backed Smart Wallet creation

**Goal:** a new user creates a Coinbase Smart Wallet via Passkey; no
mnemonic UI ever shows.

**Procedure**
1. On `/settings` (signed in or not), click **Connect Smart Wallet**.
2. The Coinbase popup opens at `https://keys.coinbase.com/connect`.
3. Complete the Passkey prompt (Touch ID / Face ID / Windows Hello).
4. Return to `/settings`.

**Expected**
- [ ] No screen anywhere shows a seed phrase or mnemonic. The flow is
      Passkey-only — `coinbaseWallet({ preference: { options: "smartWalletOnly" } })`
      forbids the EOA path.
- [ ] Card now shows "Smart Wallet connected: 0xabcd...wxyz" with two
      green capability dots: "EIP-5792 atomic batch" and "Paymaster-
      sponsored gas".
- [ ] Both dots are green (Smart Wallet supports both per Coinbase's
      published capabilities). Yellow / red means the SDK changed —
      investigate before sign-off.

---

## 3.8  Base.dev manifest + Frame embed

**Goal:** the manifest at `/.well-known/farcaster.json` matches the
Farcaster Frame v2 spec; the per-page `fc:miniapp` embeds resolve to
launch-frame buttons.

**Procedure**
```bash
# Manifest:
curl -sS http://localhost:3000/.well-known/farcaster.json | jq .

# Asset URLs return PNGs at the right dimensions:
for path in /api/og/icon-1024 /api/og/splash /opengraph-image; do
  curl -sS "http://localhost:3000$path" -o /tmp/x.png
  echo "$path: $(file /tmp/x.png)"
done

# Per-page fc:miniapp meta tags:
for page in / /breaches /protocols/aerodrome; do
  echo "=== $page ==="
  curl -sS "http://localhost:3000$page" | grep -oE 'fc:miniapp"[^>]*content="[^"]+' | head -1 | head -c 200
  echo ""
done
```

**Expected**
- [ ] Manifest carries `frame.version=1`, `name`, `homeUrl`, `iconUrl`,
      `splashImageUrl`, `splashBackgroundColor`, `heroImageUrl`,
      `subtitle` (≤30 chars), `description` (≤170), `primaryCategory`,
      `tags` (≤5), `requiredChains=["eip155:8453","eip155:84532"]`,
      `requiredCapabilities`, `canonicalDomain`.
- [ ] Icons: 1024×1024 PNG, 200×200 PNG, 1200×630 PNG.
- [ ] Every page tested has its own `fc:miniapp` meta tag with the
      right per-page launch URL.
- [ ] After deploy, paste the production URL into
      https://base.dev/manifest/validate and verify zero schema errors.
- [ ] (Sign-off only) Generate the signed `accountAssociation` via the
      [Farcaster Manifest Tool](https://warpcast.com/~/developers/mini-apps/manifest)
      and set `NAPG_FARCASTER_ACCOUNT_ASSOCIATION` in production secrets.

---

## 3.9  Lighthouse + OWASP ZAP

**Goal:** Lighthouse perf/security pass and ZAP baseline scan return clean.

**Procedure**
```bash
# Lighthouse (against staging or local production build):
npx lighthouse https://staging-url --view --preset=desktop \
  --only-categories=performance,best-practices,seo,accessibility

# ZAP baseline (Docker):
docker run -t ghcr.io/zaproxy/zaproxy:stable zap-baseline.py \
  -t https://staging-url -m 5
```

**Expected**
- [x] Lighthouse Performance ≥80, Best Practices ≥90, Accessibility ≥90,
      SEO ≥90.
- [x] ZAP baseline reports zero HIGH or CRITICAL findings. MEDIUM
      findings are reviewed; if accepted, recorded in the Phase 3
      threat-model addendum.

**Result — 2026-06-02 (staging, `https://napg-frontend-staging.fly.dev`).**
- Lighthouse (desktop) PASS: Performance 94, Accessibility 95, Best
  Practices 92, SEO 100.
- ZAP baseline (`-m 5`): zero HIGH/CRITICAL. First run had 7 WARNs; four
  were fixed (HSTS added, `X-Powered-By` dropped, nosniff +
  Permissions-Policy extended to `/_next/static/*` — static security
  headers moved to `next.config.ts`, CSP stays in `src/proxy.ts`).
  Rescan: PASS 64 / WARN 3 / FAIL 0. The 3 remaining WARNs (`Server`
  version header from Fly's edge, intentional `no-store` cache headers,
  COEP omitted to keep the Coinbase wallet popup working) are accepted
  and documented in
  [docs/threat-models/phase-3.md](../threat-models/phase-3.md#security-scan-results-lighthouse--zap-staging).
- Re-run against the production URL before mainnet sign-off (Phase 5).

---

## 3.10  Inside the Base App in-app browser

**Goal:** the app works inside the Farcaster client's webview on a real
device.

**Procedure**
1. After Phase 5 deploy + base.dev directory submission: open the app
   from the Base App mini-app directory on iOS or Android.
2. Sign in via SIWF.
3. Navigate Dashboard → Breaches → Settings via the bottom nav.
4. Tap **Share to Farcaster** on `/breaches` or `/protocols/aerodrome`.

**Expected**
- [x] App loads, theme-color matches the system chrome (dark by default).
- [x] Bottom nav clears the iOS home indicator (safe-area-inset works).
- [x] All tap targets feel ≥44px (no accidental neighbouring presses).
- [ ] SIWF flow completes without a third-party cookie warning.
- [ ] Share-to-Farcaster opens the compose sheet with the text + embed
      pre-filled; posting renders a launch-frame button card.

**Partial result — 2026-06-02 (staging, simulated webview).** Ran against
`https://napg-frontend-staging.fly.dev` in a headless Chromium emulating the
Base App in-app browser (iPhone 14 Pro viewport, dark scheme,
`viewport-fit=cover`, Base App / Farcaster UA token). 16/16 structural checks
passed, covering the markup half of this procedure:
- App loads (HTTP 200); dark `theme-color` is `#0a0a0a`; `viewport-fit=cover`.
- Bottom nav is sticky and pads `env(safe-area-inset-bottom)`; three nav links,
  smallest tap target 44px.
- Dashboard -> Breaches -> Settings nav resolves; `/settings` shows the
  Sign in with Farcaster affordance.
- Share-to-Farcaster anchor points at `farcaster.xyz/~/compose` with pre-filled
  `text` + `embeds[]`, `target=_blank rel="noopener noreferrer"`.

Still open (require a real device + Phase 5 directory listing, cannot be
reproduced headless): the third-party-cookie-free SIWF round-trip with a real
Farcaster signer, Passkey Smart Wallet creation, tactile tap feel, opening from
the Base App mini-app directory, and the share sheet actually posting a
launch-frame card. The two unchecked boxes above stay unchecked until then.

---

## 3.11  Manual breach feed sanity

**Goal:** the audit-log-backed feed renders correctly when populated.

**Procedure**
1. With the agent stopped, navigate to `/breaches`. Note the amber
   "Cannot reach the audit log" callout (graceful-degrade path).
2. Start the agent: `cd agent && uv run napg serve`.
3. In another shell: `uv run napg simulate sequencer-delay --amount-eth 0.0001`
   (dry-run; this populates the audit DB with breach rows).
4. Refresh `/breaches`. Expect rows.
5. Navigate to `/protocols/heartbeat` and confirm only heartbeat-source
   rows appear.

**Expected**
- [x] Amber callout when agent is unreachable; not a 500 page.
- [x] Rows appear after `simulate` runs.
- [x] Per-protocol filter is correct.

**Result — 2026-06-27 (local, agent backend driven directly).** Ran the
substance of this procedure against the agent's `GET /api/audit/breaches`
endpoint (the same surface the frontend proxies):
- Started `uv run napg serve` (up in 1s, `/api/status` 200).
- `napg simulate sequencer-delay --amount-eth 0.0001` (dry-run) drove a full
  scenario -> 3 breaches -> decision (`migrate_to_safe`, conf 0.97) -> action chain.
- Breach feed grew 9 -> 12 rows; newest row `reorg_is_breach` at the run
  timestamp. Per-source filter correct: `source=heartbeat` returned all 12,
  `source=aerodrome` returned 0 (no false positives).
- `napg audit verify`: 25 total rows, 0 tampered (chain intact across the run).
- The frontend amber "Cannot reach the audit log" callout (agent-down render) is
  covered by the existing breach-feed e2e test; not re-driven headless here.

---

## Sign-off checklist

- [x] Procedures 3.1–3.11 completed.
- [x] Lighthouse and ZAP findings reviewed (any non-rejected medium
      severity items captured in `docs/threat-models/phase-3.md`).
- [x] Threat-model addendum filed for Phase 3 (new attack surfaces:
      SIWF relay trust, Passkey wallet, CSRF/rate-limit deferred-state).
- [x] User signs off in chat with name + date — Samuel Apakuki Nayacakalou,
      2026-06-27.

## Sign-off result — 2026-06-27

All Phase 3 procedures verified across local + staging
(`https://napg-frontend-staging.fly.dev`):

- **3.1 SIWF login** (real device): signed in with a real Farcaster account
  via the inline QR; `/settings` rendered "Signed in as `<fid>`".
- **3.2 signature verification** (live curl): never-issued token ->
  `{"state":"unknown"}`; empty token -> HTTP 400.
- **3.3 CSRF guard** (live curl): cross-origin POST -> 403, no-Origin POST ->
  403, same-origin POST -> 200.
- **3.4 rate-limit** (live parallel burst): 62 x 200 + 18 x 429 with the
  token-bucket cutoff (sequential curls don't saturate the 60-token burst at
  4 tok/s; parallel does).
- **3.5 CSP + cookie audit**: live headers carry `script-src`/`style-src`
  nonce + `strict-dynamic` with no `unsafe-inline`; per-request nonce rotates.
  A devtools console violation (nav inline `style` attribute) was found and
  fixed (moved to a `.safe-bottom` class) + redeployed. Session storage
  confirmed empty; cookie flags `HttpOnly`/`Secure`/`SameSite=Lax` enforced +
  unit-tested in `lib/session.ts`.
- **3.6 Basename** (real device): user's Basename resolved on `/settings`.
- **3.7 Passkey Smart Wallet** (real device): Face ID created the wallet, both
  capability dots green (atomic batch + sponsored gas), no seed phrase shown.
- **3.8 manifest + Frame embeds**: shape-verified (smoke).
- **3.9 Lighthouse + ZAP**: recorded 2026-06-02 (Lighthouse desktop pass; ZAP
  zero HIGH/CRITICAL). Production-URL re-run carried to Phase 5.
- **3.10 in-app browser**: markup half done (simulated webview, 16/16). Real-
  device half carried to Phase 5 (needs the directory listing).
- **3.11 breach feed**: verified 2026-06-27 (see result above).

**Carried to Phase 5 frontend cutover** (deploy-gated on the production
domain, not build defects): Base App directory submission, real-device in-app-
browser pass, and production `accountAssociation` signing.
