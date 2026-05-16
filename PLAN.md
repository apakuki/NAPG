# NAPG Starting Plan

NetAssure Protocol Guardian: autonomous Protocol Service Assurance agent for the Coinbase Base ecosystem. This document is the source-of-truth phased plan. Tick boxes as work lands. Update the architecture/library notes inline when reality drifts from the brief.

Reference: [Building on Coinbase Base Ecosystem.pdf](Building on Coinbase Base Ecosystem.pdf), [CLAUDE.md](CLAUDE.md).

## Operating principles

- Python 3.10+ for the agent core, Next.js in `frontend/`.
- MPC wallets only. Private keys never enter agent code. All signing goes through CDP TEE.
- Every autonomous decision writes a permanent audit record (the "why" must be recoverable).
- No emojis. Anywhere. Code, commits, README, UI.
- No defensive programming, no speculative features, no premature abstraction.
- Aim for 80% minimum unit coverage on backend modules; Playwright for frontend integration.
- Get user sign-off at the end of each phase before starting the next.

## Phase 0: Repo scaffolding

Lay groundwork so subsequent phases have somewhere to land code.

### Substeps
- [x] Add `.gitignore` (Python, Node, env files, build artefacts, `.venv/`, `.next/`, coverage)
- [x] Add root `README.md` (one-paragraph positioning + how to run)
- [x] Create `agent/` directory for the Python core (`pyproject.toml` via uv, `napg/`, `tests/`)
- [x] Create `frontend/` directory with Next.js 16 + Tailwind 4 + TypeScript (App Router, src/, ESLint)
- [x] Add `.env.example` listing required keys (Anthropic, CDP, Base RPC, Tenderly, 0x, Farcaster)
- [x] Add `scripts/` with `start.sh` and `stop.sh` placeholders
- [x] Wire pytest + ruff (agent) and eslint + vitest + Playwright (frontend)
- [x] Add GitHub Actions CI (`.github/workflows/ci.yml`) running both pipelines
- [x] Update CLAUDE.md "Commands" section with the toolchain

### Tests
- [x] `uv run pytest` runs cleanly (1 smoke test passing)
- [x] `npm run lint && npm run test && npm run build` all green in `frontend/`
- [ ] Pre-commit or CI hook rejects emoji introduction (deferred — optional)

### Success criteria
- [x] Both Python and Next.js toolchains run green with placeholder code
- [ ] `git clone` -> install -> run on a fresh machine takes under 10 minutes (untested, expected to hold)
- [ ] User signs off on the scaffolding layout

## Phase 1 (Wk 1-2): Prototype and Logic Core

Build the monitoring brain. Heartbeat Base Sepolia RPC, watch Aerodrome and Seamless protocol state, surface a Service Assurance Dashboard. End-state: agent detects a simulated sequencer delay and moves testnet funds to a safe contract.

### Substeps
- [ ] Implement Web3.py RPC heartbeat: latency, block height, reorg detection against Base Sepolia
- [ ] Add AgentiPy-style liquidity probe for Aerodrome pool(s) via the 0x API
- [ ] Add Seamless lending-market state poller (utilization, oracle freshness)
- [ ] Define "Service Level Breach" thresholds in a config file (latency, peg deviation, revert-rate, oracle staleness)
- [ ] Wire LangChain + Claude (Opus-class via OpenRouter or Anthropic SDK) as the reasoning layer; inputs = protocol state JSON, output = decision intent
- [ ] Integrate CDP AgentKit for testnet wallet creation and a `move_to_safe_contract` action
- [ ] Build the Service Assurance Dashboard (Next.js) hitting a FastAPI read endpoint exposed by the agent
- [ ] Stand up audit-trail writer (append-only JSONL or SQLite; one row per decision: timestamp, inputs, reasoning, action, tx hash)
- [ ] Simulate a sequencer delay (mock RPC) and verify the migration path runs end-to-end on Sepolia

### Tests
- [ ] Unit tests for each monitor (RPC, pool, lending) with mocked responses, >=80% coverage
- [ ] Unit tests for breach-threshold evaluation
- [ ] Integration test: full pipeline from mocked sequencer-delay event to a Sepolia testnet tx
- [ ] Playwright smoke test on the dashboard route
- [ ] Audit-log test: every autonomous decision produces a recoverable record

### Success criteria
- [ ] Dashboard renders live Sepolia data without errors
- [ ] Agent detects the simulated sequencer delay and submits a migration tx on Sepolia
- [ ] Audit log contains a complete, human-readable explanation for the migration
- [ ] User signs off on Phase 1

## Phase 2 (Wk 3): Security Layer

Wrap every signing path in AgentShield's 4-stage validation. Nothing reaches the wallet without passing all four gates.

### Substeps
- [ ] Stage 1 - Intent Judge: LLM-side check that the proposed action matches the stated goal
- [ ] Stage 2 - Policy Validation: per-tx caps, token allowlist, destination denylist, daily-spend ceiling
- [ ] Stage 3 - Tenderly Simulation: dry-run the tx, parse state diff, fail closed on revert or unexpected balance change
- [ ] Stage 4 - Honeypot Detection: BUY-then-SELL simulation on the target token before any real swap
- [ ] Centralise the four stages behind a single `validate_or_die(tx)` interface used by every action
- [ ] Add policy-config file with sensible testnet defaults
- [ ] Add denylist-loader (start with a static list, leave room for a feed)

### Tests
- [ ] Unit tests for each stage in isolation, >=80% coverage
- [ ] Integration test: a tx that fails policy is blocked and audit-logged
- [ ] Integration test: a known honeypot token fails Stage 4
- [ ] Negative test: removing any stage breaks the gate (validation is mandatory)
- [ ] Replay test: same input -> same decision (deterministic where it should be)

### Success criteria
- [ ] Agent blocks a tx to a denylisted address
- [ ] Agent correctly fails the BUY-then-SELL honeypot probe on a known bad token
- [ ] No signing path bypasses `validate_or_die`
- [ ] User signs off on Phase 2

## Phase 3 (Wk 4): Frontend and Social Distribution

Make NAPG discoverable in the Base App and authable without a password.

### Substeps
- [ ] Build out the Next.js app: dashboard, protocol detail pages, breach feed, settings
- [ ] Tailwind theme tuned for the Base App in-app browser (mobile-first, dark mode)
- [ ] SIWF (Sign In With Farcaster) auth wired up
- [ ] Basenames (BNS) resolution for display
- [ ] CDP MPC Smart Wallet via Passkey; verify EIP-5792 batch and sponsored gas
- [ ] Base.dev metadata + mini-app manifest
- [ ] Submit to the Base App mini-app directory
- [ ] Add "Share to Farcaster" affordance on Protocol Health Reports

### Tests
- [ ] Playwright e2e: SIWF login -> dashboard -> trigger a manual assurance check
- [ ] Wallet-creation test against CDP testnet
- [ ] Lighthouse pass on the dashboard (mobile)
- [ ] Manual check inside the Base App in-app browser

### Success criteria
- [ ] User can log in with Farcaster and see their Basename
- [ ] Passkey-backed MPC wallet is created with no seed phrase exposed
- [ ] App is discoverable inside the Base App mini-app directory
- [ ] User signs off on Phase 3

## Phase 4 (Wk 5): Monetization and Attribution

Turn the agent into a revenue surface.

### Substeps
- [ ] Register Builder Code on Base.dev
- [ ] Suffix calldata on every NAPG-originated tx for ERC-8021 attribution
- [ ] Stand up x402 endpoints: agents pay USDC to receive an Assurance Report
- [ ] Define the Assurance Report schema (protocol, window, breaches, recommendation, signature)
- [ ] Implement Guardian Mode subscription scaffolding (no billing UI yet, just the entitlement check)
- [ ] Document the Native USDC treasury yield path on Base App (~3.35% APY baseline)

### Tests
- [ ] On-chain check: a NAPG tx on Sepolia carries the correct Builder Code suffix
- [ ] x402 integration test: a paying client agent gets a signed Assurance Report; a non-paying one gets HTTP 402
- [ ] Entitlement-check unit tests for Guardian Mode

### Success criteria
- [ ] Builder Code registered and visible on Base.dev
- [ ] x402 endpoint produces a valid, signed Assurance Report on payment
- [ ] User signs off on Phase 4

## Phase 5 (Wk 6): Mainnet launch

Production cutover and growth loop.

### Substeps
- [ ] Deploy agent to a production host (Fly.io, Render, or AWS - pick during the phase)
- [ ] Mainnet RPC, mainnet AgentShield policy (tighter caps than testnet)
- [ ] Migrate Aerodrome and Seamless monitors to Base mainnet
- [ ] Production audit-log storage with retention policy
- [ ] Cast-Driven Onboarding Loop: scheduled Farcaster posts on protocol events and weekly health reports
- [ ] On-call runbook: how to pause the agent, rotate keys, respond to a breach false-positive
- [ ] Status page at a public URL

### Tests
- [ ] Smoke run on mainnet with caps set to dust amounts
- [ ] Failover test: kill the agent, confirm monitors recover cleanly on restart
- [ ] Backup/restore test for the audit log
- [ ] Manual end-to-end: a real Base App user signs in, sees live data, opts into Guardian Mode

### Success criteria
- [ ] Agent runs unattended on mainnet for 72 hours with no incidents
- [ ] First weekly Protocol Health Report is posted to Farcaster
- [ ] At least one external agent has paid via x402 for an Assurance Report
- [ ] User signs off on launch

## Resolved decisions (2026-05-16)

- LLM provider: **direct Anthropic SDK** (Claude Opus-class). Keep prompt-caching first-class.
- Audit-log substrate: **SQLite from day one**. One table per concern, append-only writes.
- Production host: **Fly.io**. Dockerfile deploy, persistent volume for the audit DB.
- CI: **GitHub Actions wired up in Phase 0**. Lint + tests on every push from day one.
- Phase 1 monitoring targets:
  - Aerodrome: `USDC/USDbC` stable pool
  - Seamless: `USDC`, `WETH`, `cbETH` supply/borrow markets
