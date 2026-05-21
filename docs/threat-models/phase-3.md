# Phase 3 threat model — Frontend and Social Distribution

Scope: the Next.js 16 frontend (`frontend/`), the SIWF auth flow, the
Coinbase Smart Wallet (Passkey) integration, server-side Basenames
resolution, the Farcaster Frame v2 manifest + per-page embeds, the
Share-to-Farcaster compose intent, and the cross-cutting guards (CSRF,
rate-limit, redact) on the auth surface.

This document is the written threat-model delta required by
[PLAN.md](../../PLAN.md#cross-cutting-security-baseline) for Phase 3
sign-off. It builds on [phase-2.md](phase-2.md) by adding the surface
area introduced by a browser-rendered SPA, a cookie-authenticated
session, a third-party relay (`farcaster.xyz`), a third-party identity
provider (Coinbase Smart Wallet via `keys.coinbase.com`), and a public
manifest catalog (base.dev).

## New surface introduced this phase

- An HTTP-served HTML surface at `/`, `/breaches`, `/protocols/[id]`,
  `/settings` (the Service Assurance Dashboard, breach feed, per-protocol
  detail, and identity / wallet settings).
- A JSON manifest at `/.well-known/farcaster.json`, plus three
  ImageResponse-generated assets at `/api/og/icon-1024`, `/api/og/splash`,
  and `/opengraph-image`.
- Auth endpoints: `POST /api/auth/siwf/start`, `GET /api/auth/siwf/poll`,
  `GET /api/auth/session`, `POST /api/auth/signout`.
- Data proxy endpoints: `GET /api/status`, `GET /api/audit/breaches` -- both
  forward server-side to the agent at `NAPG_API_URL` and stay off-browser.
- An outbound HTTPS path to the Farcaster relay (`farcaster.xyz`) for the
  SIWF channel + signature-verification round-trip.
- An outbound HTTPS path to the Coinbase Smart Wallet popup at
  `keys.coinbase.com` (window.open + postMessage; never iframe-embedded).
- An outbound HTTPS path to Base mainnet RPC for Basenames reverse
  resolution.
- One session cookie (`napg_session`), HMAC-SHA256 signed with
  `NAPG_SESSION_SECRET`, carrying `{fid, address, exp}`.
- Per-request CSP nonces minted by `frontend/src/proxy.ts` (Next.js 16's
  renamed middleware).
- Two new server-side stores in-memory: the SIWF pending-channel map
  (5-min TTL, single-instance) and the rate-limit token buckets
  (single-instance Map; ~60-token burst at 4 tok/s per IP+route).
- Two new env vars: `NAPG_SESSION_SECRET` (HMAC key, wallet-grade) and
  `NAPG_FARCASTER_ACCOUNT_ASSOCIATION` (optional; signed JSON triplet that
  binds the deployed domain to a Farcaster custody key).

## Trust model

- The Next.js server is trusted; the browser is hostile.
- `NAPG_SESSION_SECRET` is wallet-grade material -- a leak lets an
  attacker mint cookies impersonating any fid. Same protection class as
  the Phase 2 policy signing key.
- The Farcaster relay (`farcaster.xyz`) is hostile-on-the-margin: we use
  it as a transport for the channel + status round-trip, but every
  signature is verified locally with `@farcaster/auth-client`'s
  `verifySignInMessage` against the *server-generated* nonce, not
  anything the relay echoes back. A compromised relay cannot mint a
  passing session.
- The Coinbase Smart Wallet popup origin (`keys.coinbase.com`) is trusted
  within the wallet flow: the user authenticates there with a Passkey,
  the key material never leaves their device's secure enclave, and the
  flow communicates back via `postMessage`. We force
  `preference.options: "smartWalletOnly"` so the EOA / mnemonic path is
  unreachable.
- Base mainnet RPC is treated as ordinary internet infrastructure for
  Basenames lookups. The reverse-resolution result is forward-verified
  before display; a misbehaving RPC can only cause a null-fallback, not
  a wrong-name render.
- The Next.js dev server's `.env.local` and `NAPG_SESSION_SECRET` are
  protected by workstation hygiene at Phase 3; Phase 5 moves them to
  `fly secrets`.

## Threats and failure paths

### SIWF channel-token replay

**What that looks like:** an attacker observes a channel token (logs,
referer, screen share) and races the legitimate user to call
`/api/auth/siwf/poll` first to harvest the signed payload and bind it
to *their* session.

**Mitigations:**

- The channel-token map is single-use: `pollChannel` deletes the entry
  on any verification attempt that returns a completed payload, success
  or fail (replay defence). Covered by
  `test_replay_after_completed_returns_unknown`.
- The session cookie is set inside the same request that consumed the
  channel, so the user who polls first gets the cookie. There is no
  separate "claim" step.
- The relay's status endpoint returns the user's signed message + the
  recovered address; even if an attacker won the race they would land a
  session for *the legitimate user's fid + address*, not for themselves
  -- a denial of service at most.

**Residual risk:** the attacker could repeatedly start their own
channel and abandon the user's. Rate-limit and the single-use deletion
together cap the blast radius to "user has to retry sign-in".

### Session cookie forgery

**What that looks like:** an attacker constructs a `napg_session` cookie
claiming a different fid + address and the server trusts it.

**Mitigations:**

- The cookie body is `base64url(JSON({fid,address,exp})).hex(HMAC-SHA256)`.
  `verifySessionToken` computes the HMAC with `NAPG_SESSION_SECRET` in
  constant time via `timingSafeEqual` and rejects any mismatch.
- The address is range-checked against `^0x[0-9a-fA-F]{40}$` so a forged
  cookie body cannot smuggle in a non-address string that the proxy might
  later treat as RPC input.
- Cookie flags are `HttpOnly` (JS can't read it), `SameSite=Lax` (no
  cross-site auto-submission), `Secure` in production, no `Domain` so the
  scope is the exact eTLD+1.

**Residual risk:** a leak of `NAPG_SESSION_SECRET` lets the attacker mint
arbitrary cookies. Phase 3 protection is env-var workstation hygiene.
Phase 5 moves the secret to Fly secrets + adds rotation.

### CSRF on state-changing routes

**What that looks like:** a hostile site loads `<img>`, `<form>`, or
`fetch` against `/api/auth/signout` or `/api/auth/siwf/start` on the
user's behalf and lands a state change.

**Mitigations:**

- `lib/csrf.ts::assertSameOrigin` rejects non-safe methods whose
  `Origin` header (or `Referer` origin) does not exactly match the
  request's own scheme + host. Both missing => 403. Same-origin SPA
  fetch() always sends `Origin`; cross-origin requests cannot suppress
  it.
- `SameSite=Lax` on `napg_session` is the cookie-layer defence in depth:
  even if the CSRF guard had a bug, the browser would not auto-attach
  the cookie to a cross-site POST.
- All four state-changing/auth routes (`siwf/start`, `siwf/poll`,
  `signout`, plus future `/api/agent/*`) flow through a single
  `applyGuards` wrapper -- there is no second path that could miss the
  check.

**Residual risk:** GET endpoints with side-effects -- `/api/auth/siwf/poll`
sets the session cookie on completed. It is exempt from CSRF because:
(a) the request needs a fresh server-issued `channelToken` that the
attacker has no way to obtain, (b) the relay's response carries the
user's signature recovered from their wallet -- a CSRF'd poll would
land a session for the user, not the attacker. Documented under
accepted risks; revisit if the poll surface grows.

### Rate-limit bypass via X-Forwarded-For spoofing

**What that looks like:** an attacker sends `X-Forwarded-For:
203.0.113.5` (or rotates through fake IPs) to dodge the per-IP bucket.

**Mitigations:**

- `clientIpFromHeaders` reads `X-Forwarded-For` left-most, then
  `X-Real-IP`, then falls back to `local`. In dev this is sufficient
  because the request hits Next.js directly with no real proxy.
- In production, the deployment platform (Fly.io's edge or Cloudflare
  in front) sets `X-Forwarded-For` itself; trusting it requires
  validating that the request actually transited a known CDN.

**Residual risk:** Phase 3 trusts XFF unconditionally. Phase 5 pins a
`NAPG_TRUSTED_PROXY_HEADER` env var and only honours XFF when a known
shared secret is present. Documented under accepted risks.

### CSP regression / inline-script bypass

**What that looks like:** a future change introduces an inline `<script>`,
removes the `script-src 'self' 'nonce-...' 'strict-dynamic'` directive,
or wires up a third-party `<script src>` without an SRI hash. An XSS
payload then executes.

**Mitigations:**

- `frontend/src/proxy.ts` mints a per-request nonce and applies the
  strict CSP on every HTML route. Static assets, `/api/og/*`, and
  `/.well-known/farcaster.json` are excluded by the matcher because they
  don't need CSP.
- `frontend/e2e/csp.spec.ts` (existing Phase 3 test) asserts the
  presence of `script-src` + `'strict-dynamic'` and the absence of
  `'unsafe-inline'` outside dev, plus that the nonce rotates between
  requests.
- A live grep verifies that there are zero `<script src="https://..."`
  third-party scripts anywhere in `frontend/src/`. All JS is bundled
  through npm with content-addressed integrity at install time via
  `package-lock.json`.

**Residual risk:** dev mode adds `'unsafe-eval'` to `script-src`
(required by React devtools) and `'unsafe-inline'` to `style-src`
(required by Tailwind 4's dev pipeline). Both flip off in production via
`NODE_ENV === "production"` branching in `proxy.ts`. Sign-off must
confirm the production deploy carries the strict variant.

### Basename squatter rendering the wrong name

**What that looks like:** a malicious user sets their reverse record
to `vitalik.base.eth` (or another well-known name) and we naively
render that for their address.

**Mitigations:**

- `lib/basenames.ts::resolveBasename` does reverse + forward
  verification: after reading `L2Resolver.name(reverseNode)`, it
  computes `namehash(name)` and calls `L2Resolver.addr(forwardNode)`.
  The result must equal the original address (lowercase compare) or
  the function returns null and the UI falls back to the truncated
  `0xabcd...wxyz` form.
- The forward-verify path is covered by
  `test_returns_null_when_forward_resolution_does_not_match`.

**Residual risk:** none significant. The squatter scenario is the
canonical ENS attack and the forward-verify is the canonical defence.

### Sensitive data leakage through API responses

**What that looks like:** a future agent schema change (or proxy
mutation) adds a token-shaped field to a JSON response and the browser
caches it / a CDN logs it.

**Mitigations:**

- `lib/redact.ts::redactResponse` walks every JSON body returned through
  `/api/status` and `/api/audit/breaches` recursively, masking values
  under known-sensitive keys (`password`, `secret`, `token`, `api_key`,
  `signature`, `mnemonic`, ...), stripping URL credentials, and partially
  masking long base64-shaped tokens. Public onchain identifiers
  (addresses and tx hashes) are exempt by explicit regex.
- The agent's Python side already redacts its own outputs (`napg.redact`
  + per-card Pydantic schemas in `napg.api` that intentionally don't
  surface secrets). The frontend redact is the second gate at the Next
  boundary.

**Residual risk:** the redact heuristics will not catch a *new* shape of
sensitive data that doesn't match a known key or token pattern.
Compensated by code review on new agent schema fields and by the
per-card Pydantic models on the agent side, which forbid unknown extra
fields.

### Phishing via the Share-to-Farcaster intent URL

**What that looks like:** a user clicks the Share-to-Farcaster button
and is redirected somewhere other than `farcaster.xyz`.

**Mitigations:**

- The compose intent URL is built by `buildComposeIntentUrl` which
  hard-codes `https://farcaster.xyz/~/compose` as the base. The text
  and embed URL are URL-encoded via `URLSearchParams` so a malicious
  embed URL cannot break out of its parameter slot.
- The anchor ships `target="_blank" rel="noopener noreferrer"` so the
  destination page cannot read `window.opener` or inherit our session.
- NAPG never signs the cast on the user's behalf -- the user reviews
  and posts manually on `farcaster.xyz`. No API key, no signer, no
  auto-post path.

**Residual risk:** none significant. The compose URL is a deterministic
function of source code; a phishing intent URL would require an
attacker to ship a different `buildComposeIntentUrl` (i.e., compromise
the source).

### In-app browser sandbox differences

**What that looks like:** the Base App's webview blocks third-party
cookies, treats `localStorage` as ephemeral, or applies different CSP
rules than a desktop Chrome. The app then silently breaks for users who
arrive via Farcaster.

**Mitigations:**

- The session cookie is *first-party* (set on the same domain the user
  is visiting) and `HttpOnly`. It does not depend on third-party cookie
  policy.
- Zero use of `localStorage` / `sessionStorage` for anything
  load-bearing (`grep` verified). The Coinbase Wallet SDK uses
  localStorage internally for public connection state; that is
  ephemeral by design and does not affect authentication.
- `viewportFit: "cover"` + safe-area-inset padding on the bottom nav
  means iOS home-indicator clearance works correctly inside the in-app
  browser.
- Manual procedure 3.10 in
  [docs/manual-tests/phase-3.md](../manual-tests/phase-3.md) is the
  sign-off gate -- the real-device check is non-negotiable before
  shipping.

**Residual risk:** until the in-app browser test passes on real
hardware, this risk is open. Phase 3 sign-off depends on it.

### Server-side Frame embed via spoofed Host header

**What that looks like:** a request arrives with a forged `Host` or
`X-Forwarded-Host` header (e.g. `Host: evil.example`). The manifest
route returns absolute URLs pointing at `evil.example`, and if a Farcaster
client caches the manifest, the user lands on the attacker's domain.

**Mitigations:**

- The manifest, the per-page Frame embed, and `lib/breach-feed.tsx` all
  derive the origin from the *request* headers. In production behind
  Fly.io's edge, the host header is set by the edge proxy; an attacker
  cannot inject a forged value.
- The manifest's `canonicalDomain` field is also derived from the same
  header; the Farcaster client cross-checks `canonicalDomain` against
  the URL the manifest was fetched from and rejects mismatches.

**Residual risk:** in dev mode the host header is whatever the client
sends. Acceptable -- there is no production manifest URL to spoof a
Farcaster client into trusting.

## Threats and mitigations summary

| Threat | Mitigation |
|---|---|
| SIWF channel-token replay | Single-use deletion on poll; session-cookie set inline |
| Session cookie forgery | HMAC-SHA256 over canonical payload; strict address regex |
| CSRF on state-changing routes | Origin/Referer match + SameSite=Lax cookie; single `applyGuards` chokepoint |
| Rate-limit bypass via XFF | Token-bucket per IP; Phase 5 pins trusted-proxy header |
| CSP regression | Per-request nonce; e2e CSP spec; zero third-party scripts |
| Basename squatter | Reverse + forward verification; lowercase compare |
| API response leakage | `redactResponse` at the Next boundary; agent-side Pydantic schemas |
| Phishing via share intent | Hard-coded `farcaster.xyz`; URL-encoded params; `rel="noopener"` |
| In-app browser sandbox | First-party HttpOnly cookies; no load-bearing localStorage; viewport-fit cover |
| Spoofed Host on manifest | Edge proxy sets Host in prod; canonicalDomain cross-check by client |

## Accepted risks (deferred items)

- **Lighthouse + OWASP ZAP scan** deferred to sign-off: needs a deployed
  staging URL. Documented in
  [docs/manual-tests/phase-3.md §3.9](../manual-tests/phase-3.md#39--lighthouse--owasp-zap).
- **accountAssociation signature** absent on the manifest until the
  user generates the signed triplet via the Farcaster Manifest Tool
  with their custody key. The manifest still parses and per-page Frame
  embeds still render; base.dev marks the entry as unverified until
  the field lands.
- **Iconography alpha channel** -- the Frame v2 spec says `iconUrl` is
  PNG with no alpha; `next/og`'s ImageResponse always emits RGBA. The
  pixels are fully opaque so the image renders correctly and base.dev
  is historically lenient. Stripping the alpha channel cleanly would
  mean adding `sharp` as a runtime dep, deferred to Phase 5 polish.
- **In-memory SIWF channel store + rate-limit buckets** are
  single-instance. Phase 5 mainnet cutover swaps both for a shared
  Redis backend (interface stays stable across the swap).
- **Trusted-proxy validation on X-Forwarded-For** deferred to Phase 5:
  Phase 3 trusts XFF unconditionally, which is correct in dev (no proxy)
  but would let an attacker forge IPs in production. The Phase 5
  deploy pins a `NAPG_TRUSTED_PROXY_HEADER` and only honours XFF when
  the shared secret is present.
- **Real-device test inside the Base App in-app browser** deferred to
  sign-off (manual test 3.10). All the structural defences are in
  place, but the actual rendering and behaviour can only be verified on
  hardware with the Base App installed.
- **Sub-second CSRF / rate-limit race windows.** The bucket reads +
  decrements are not atomic across concurrent requests. At Phase 3
  single-instance volumes this is invisible; Phase 5 Redis swap closes
  it via INCR + EXPIRE.
- **Branch protection on `main`** still deferred per
  [phase-0.md](phase-0.md#accepted-risks). A hostile contributor with
  push access could ship a CSP regression, replace the public key, or
  remove the `applyGuards` chokepoint. Mitigated by solo-dev mode (no
  collaborators) and gitleaks pre-commit.

## Next phase delta

Phase 4 (Monetization and Attribution) introduces an x402 payment
surface (HTTP 402 + USDC receipts), Assurance Report signing with a
*dedicated reporting key* distinct from the wallet, ERC-8021 Builder
Code calldata suffixing on every NAPG-originated tx, and Guardian Mode
subscription entitlement checks. Its threat-model file will document:
replay defence on payment receipts (EIP-712 nonce + expiry),
idempotency-key behaviour at the API edge, key-separation between
operational wallet and reporting key, and revenue-accounting
reconciliation drift.

Phase 5 (Mainnet launch) then revisits everything Phase 3 deferred:
in-memory stores swap to Redis, `NAPG_SESSION_SECRET` and the audit
HMAC key move to Fly secrets with documented rotation, the
`NAPG_TRUSTED_PROXY_HEADER` lands, branch protection on `main` is
enabled, and the Lighthouse + ZAP scans run against the actual
production URL before flipping the agent live.
