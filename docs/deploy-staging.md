# Staging deploy (Fly.io)

How to stand up a public staging environment for NAPG on Fly.io. Two apps:

- **`napg-agent-staging`** — the FastAPI status API + orchestrator. Internal
  only (no public service); reached by the frontend over Fly's 6PN private
  network. Audit DB on a persistent volume.
- **`napg-frontend-staging`** — the public Next.js app. Server-side-proxies to
  the agent over `napg-agent-staging.internal:8080`.

Standing this up unblocks the remaining Phase 3 sign-off items that need a live
URL: Lighthouse, the OWASP ZAP baseline, the in-app-browser walkthrough, and
the Farcaster manifest `accountAssociation` (which must be signed against a
fixed production domain).

```
Internet ──▶ napg-frontend-staging (public, :3000)
                   │  server-side proxy, 6PN private network
                   ▼
             napg-agent-staging (internal only, :8080)
                   │
                   ▼  Fly volume at /data
             audit.db
```

## 0. Before you start

- **Rotate the CDP API key first.** The key that was committed to git
  (`cdp_api_key.json`, since scrubbed from history) must be treated as
  compromised. Generate a fresh CDP API key + wallet secret in the
  [CDP portal](https://portal.cdp.coinbase.com/) and use the new values below.
- These commands are yours to run — Claude cannot authenticate to your Fly
  account. In a Claude Code session you can prefix a command with `! ` to run
  it inline (handy for the interactive `fly auth login`).
- No local Docker needed; Fly builds on remote builders by default.

## 1. Install and authenticate flyctl

```bash
# macOS
brew install flyctl
# or: curl -L https://fly.io/install.sh | sh

fly auth login        # opens a browser; in Claude Code run as: ! fly auth login
fly auth whoami       # confirm you are logged in
```

## 2. Create the two apps

App names must be globally unique on Fly; if these are taken, pick your own and
update `agent/fly.toml`, `frontend/fly.toml` (`app = ...`) and the
`NAPG_API_URL` in `frontend/fly.toml` to match the agent's name.

```bash
fly apps create napg-agent-staging
fly apps create napg-frontend-staging
```

## 3. Create the agent's audit-log volume

```bash
fly volumes create napg_audit --region syd --size 1 -a napg-agent-staging
```

(`syd` matches `primary_region` in the fly.toml files. Change both if you
deploy elsewhere.)

## 4. Set the agent secrets

Everything sensitive goes through `fly secrets`, never into the image. The
status API (`/api/status`) needs the RPC + 0x keys; the rest are required only
once the deployed agent runs decision cycles or `--execute` (not the default on
staging), but set them now so nothing is missing later.

```bash
fly secrets set -a napg-agent-staging \
  ANTHROPIC_API_KEY="..." \
  CDP_API_KEY_NAME="..." \
  CDP_API_KEY_PRIVATE_KEY="..." \
  CDP_WALLET_SECRET="..." \
  CDP_AGENT_ADDRESS="0x..." \
  NAPG_SAFE_CONTRACT_ADDRESS="0x..." \
  BASE_RPC_URL="https://..." \
  BASE_SEPOLIA_RPC_URL="https://..." \
  TENDERLY_ACCOUNT_SLUG="..." \
  TENDERLY_PROJECT_SLUG="..." \
  TENDERLY_ACCESS_KEY="..." \
  ZEROX_API_KEY="..." \
  NAPG_AUDIT_HMAC_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
```

Non-secret config (`NAPG_NETWORK`, `NAPG_AUDIT_DB`) is already in
`agent/fly.toml` under `[env]`.

## 5. Deploy the agent

```bash
cd agent && fly deploy
```

Verify it is up on the private network (it has no public URL):

```bash
fly status -a napg-agent-staging
fly logs -a napg-agent-staging          # expect uvicorn listening on 0.0.0.0:8080
```

## 6. Set the frontend secret and deploy

```bash
fly secrets set -a napg-frontend-staging \
  NAPG_SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

cd frontend && fly deploy
```

The browser-side RPC endpoints default to the keyless public Base endpoints
(`https://mainnet.base.org`, `https://sepolia.base.org`) baked in at build
time. To use a private RPC on the client instead (note: it will be visible in
the bundle), pass build args:

```bash
fly deploy --build-arg NEXT_PUBLIC_BASE_SEPOLIA_RPC_URL="https://..."
```

## 7. Verify end to end

```bash
fly status -a napg-frontend-staging
fly open   -a napg-frontend-staging          # opens https://napg-frontend-staging.fly.dev

# Status API proxied through the frontend (agent stays private):
curl -s https://napg-frontend-staging.fly.dev/api/status | head

# Manifest + security headers:
curl -s https://napg-frontend-staging.fly.dev/.well-known/farcaster.json | head
curl -sI https://napg-frontend-staging.fly.dev/ | grep -i 'content-security-policy\|strict-transport'
```

You now have a fixed `https://napg-frontend-staging.fly.dev` origin for the
Phase 3 sign-off checks (Lighthouse, ZAP, in-app browser, manifest
`accountAssociation` signing).

## Troubleshooting

- **Frontend 502 / "cannot reach agent"** -> agent machine stopped or wrong
  app name in `NAPG_API_URL` -> `fly status -a napg-agent-staging`; confirm the
  `.internal` host matches the agent app name exactly; keep
  `min_machines_running = 1` on nothing-stops the agent.
- **`fly deploy` build fails on `uv sync`** -> a dependency needs to compile
  from sdist and the slim image lacks a toolchain -> confirm `uv.lock` resolves
  to wheels; if not, add the missing system lib to the agent Dockerfile.
- **Frontend build OOMs on the remote builder** -> bump the builder with
  `fly deploy --build-only` diagnostics or set a larger builder VM; the app VM
  memory (512mb) is separate from the build VM.
- **`/api/status` returns card errors** -> the agent is up but its RPC/0x
  secrets are missing or wrong -> `fly secrets list -a napg-agent-staging`;
  re-set `BASE_SEPOLIA_RPC_URL` / `ZEROX_API_KEY`.
- **Volume not mounting** -> volume region must match the machine region ->
  `fly volumes list -a napg-agent-staging`; create one in `syd` if missing.

## Teardown

```bash
fly apps destroy napg-frontend-staging
fly apps destroy napg-agent-staging      # also removes the napg_audit volume
```

Staging on `shared-cpu-1x` / 512mb with one volume is inexpensive but not free;
destroy it when not actively testing.
