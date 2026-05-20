# NAPG Starting Plan

NetAssure Protocol Guardian: autonomous Protocol Service Assurance agent for the Coinbase Base ecosystem. This document is the source-of-truth phased plan. Tick boxes as work lands. Update the architecture/library notes inline when reality drifts from the brief.

Reference: [Building on Coinbase Base Ecosystem.pdf](Building on Coinbase Base Ecosystem.pdf), [CLAUDE.md](CLAUDE.md).

## Operating principles

- Python 3.10+ for the agent core, Next.js in `frontend/`.
- MPC wallets only. Private keys never enter agent code. All signing goes through CDP TEE.
- Every autonomous decision writes a permanent audit record (the "why" must be recoverable).
- **Security is built into each layer as it lands, not bolted on at Phase 2.** Every phase has a Security subsection that must be checked before sign-off. See the cross-cutting baseline below.
- **Troubleshooting runbooks are part of the deliverable.** Every phase has a Troubleshooting subsection in the symptom -> likely cause -> diagnose -> fix format. Treat these as living docs.
- **Manual test procedures live in [docs/manual-tests/](docs/manual-tests/).** One file per phase. Update as features land.
- No emojis. Anywhere. Code, commits, README, UI.
- No defensive programming, no speculative features, no premature abstraction.
- Aim for 80% minimum unit coverage on backend modules; Playwright for frontend integration.
- Get user sign-off at the end of each phase before starting the next.

## Cross-cutting security baseline

These apply throughout the project, regardless of phase. Drift here is a release-blocker.

- **Secrets never in git.** `.env` is gitignored. Pre-commit secrets scan (gitleaks) wired in by Phase 1. CI re-scans every push.
- **Dependency CVE scanning.** `pip-audit` (agent) and `npm audit --audit-level=high` (frontend) run in CI; HIGH/CRITICAL findings fail the build.
- **Lockfile-pinned dependencies.** `uv.lock` and `package-lock.json` are committed. Dependabot keeps them moving.
- **MPC-only wallet operations.** No raw private keys, mnemonics, or signed payloads in logs, audit DB, or memory dumps. Any code path that touches signing material gets a code-review checklist tick.
- **Append-only audit log.** SQLite tables are write-once. Row-level HMAC (separate key) lands before mainnet so tampering is detectable.
- **Least-privilege API keys.** One key per environment, scoped to the minimum permissions. Rotated quarterly. Never shared across envs.
- **Redaction at log boundaries.** A single `redact()` helper strips known-sensitive fields before anything reaches stdout, files, or the audit DB.
- **Branch protection on `main`.** Required CI green. No force-push. Reviewed merges only once we leave solo-dev mode.
- **Threat-model delta at every sign-off.** "What new attack surface did this phase add and how do we handle it?" — answered in writing before the next phase starts.
- **Kill-switch from Phase 2 onwards.** A single signed message or env var halts all signing immediately.

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

### Security
- [x] `.gitignore` excludes `.env`, `.env.local`, `.venv/`, `node_modules/`, `audit.db*`
- [x] Add `SECURITY.md` at repo root (disclosure policy + contact)
- [x] Enable Dependabot for both `pip` and `npm` ecosystems (configured for `uv`, `npm`, and `github-actions`)
- [x] Add `gitleaks` pre-commit hook and a CI job that re-scans on every push
- [x] CI runs `pip-audit` (agent) and `npm audit --audit-level=high` (frontend); fail on HIGH/CRITICAL
- [x] Enable branch protection on `main`: require CI green, no force-push, no direct push (once collaborators land) — deferred 2026-05-17 per [Phase 0 threat model](docs/threat-models/phase-0.md#accepted-risks); blocked on private repo without GitHub Pro and not needed in solo-dev mode. Revisit when a second collaborator lands, when the repo goes public, or before mainnet (Phase 5)
- [x] Document the threat model for the scaffolding layer: only the dev box is in scope; no production attack surface yet ([docs/threat-models/phase-0.md](docs/threat-models/phase-0.md))

### Tests
- [x] `uv run pytest` runs cleanly (1 smoke test passing)
- [x] `npm run lint && npm run test && npm run build` all green in `frontend/`
- [x] Manual test procedures completed: [docs/manual-tests/phase-0.md](docs/manual-tests/phase-0.md) (0.2-0.6, 0.8 ticked locally; 0.1 fresh-clone timing and 0.7 CI green pending user push)
- [ ] Pre-commit or CI hook rejects emoji introduction (deferred — optional)

### Success criteria
- [x] Both Python and Next.js toolchains run green with placeholder code
- [x] `git clone` -> install -> run on a fresh machine takes under 10 minutes (verified 2026-05-17: ~8s total on a warm-cache laptop)
- [x] Security baseline checklist complete (Dependabot, secrets scan, dep audit, branch protection) — branch protection formally deferred 2026-05-17 per threat-model accepted risks; all other baseline items in place
- [x] User signs off on the scaffolding layout — Samuel Apakuki Nayacakalou, 2026-05-17 (authorized in chat after Phase 0 checklist closed out)

### Troubleshooting
Symptom -> likely cause -> diagnose -> fix.

- **`uv sync` fails with "Python 3.10+ required"** -> uv didn't auto-install a compatible Python -> `uv python list` to see what's available -> `uv python install 3.12` then re-run `uv sync`.
- **`uv run pytest` says `ModuleNotFoundError: napg`** -> editable install missed -> `uv sync --reinstall` from inside `agent/`.
- **`ruff format --check .` fails in CI but passes locally** -> uncommitted formatter drift on another branch -> `uv run ruff format .`, commit, re-push.
- **`npm install` hangs or times out** -> registry/proxy issue -> `npm config get registry`, check network, retry with `--prefer-online`.
- **`npm run build` fails: "module not found" after dependency change** -> stale `.next` cache -> `rm -rf .next && npm run build`.
- **Vitest can't resolve `@/*` paths** -> alias mismatch in `vitest.config.ts` -> confirm `path.resolve(__dirname, "./src")` matches `tsconfig.json` `paths`.
- **Playwright e2e fails: "browser not installed"** -> chromium binary not downloaded -> `npx playwright install chromium` from `frontend/`.
- **CI fails on macOS-only line endings** -> CRLF crept in -> add `* text=auto eol=lf` to `.gitattributes`, re-normalise.
- **`.env` accidentally committed** -> immediately rotate every key in it, `git rm --cached .env`, force-push only after coordinating; treat all leaked keys as compromised.

## Phase 1 (Wk 1-2): Prototype and Logic Core

Build the monitoring brain. Heartbeat Base Sepolia RPC, watch Aerodrome and Seamless protocol state, surface a Service Assurance Dashboard. End-state: agent detects a simulated sequencer delay and moves testnet funds to a safe contract.

### Substeps
- [x] Implement Web3.py RPC heartbeat: latency, block height, reorg detection against Base Sepolia
- [x] Add AgentiPy-style liquidity probe for Aerodrome pool(s) via the 0x API
- [x] Add Morpho Blue lending-market state poller (utilization) — originally targeted Seamless, repointed 2026-05-19 after Seamless announced wind-down. Oracle-freshness half of this substep deferred to follow-up; see [Resolved decisions](#resolved-decisions-2026-05-16)
- [x] Define "Service Level Breach" thresholds in a config file — `agent/config/breaches.toml` + `napg.policy.breaches` with `BreachThresholds` model, TOML loader, and `evaluate()` over heartbeat / Aerodrome / Morpho outputs. Covers latency, block age, reorg, peg deviation, liquidity availability, market utilisation, and market accrual staleness. Revert-rate and oracle freshness are deferred until the underlying monitors land
- [x] Wire reasoning layer — `napg.reasoning.Reasoner` calls the Anthropic SDK directly (per [Resolved decisions](#resolved-decisions-2026-05-16); not LangChain). Inputs are the full probe bundle + breach evaluator output; output is a structured `Decision` (intent / rationale / confidence / supporting_breaches) extracted via Anthropic tool-use. System block uses ephemeral prompt caching; every call writes a `decision` row to the append-only audit log including cache_metadata
- [x] Integrate CDP AgentKit for testnet wallet creation and a `move_to_safe_contract` action — `napg.wallet.build_agent_wallet` returns a `CdpEvmWalletProvider` (CDP v2 server-managed MPC, keys in TEE); `napg.actions.migrate_to_safe` is the single onchain action surface, dry-run by default with `--execute` to actually submit. Every call writes an `action` row to the append-only audit log; the AgentShield 4-stage validation (Phase 2) drops in between intent and execute
- [x] Build the Service Assurance Dashboard (Next.js) hitting a FastAPI read endpoint exposed by the agent — agent side: `napg.api` is the FastAPI app, `GET /api/status` runs the three Phase 1 probes in parallel via `asyncio.to_thread` and returns per-card data or a `CardError` envelope so one broken probe never breaks the page. `napg serve` boots uvicorn on `127.0.0.1:8000`. Frontend side: `frontend/src/app/api/status/route.ts` proxies server-side to the agent (no CORS surface; backend URL stays off the wire), and `_components/status-dashboard.tsx` is a client component that polls every 10 s, pauses when the tab is hidden, and renders RPC heartbeat / Aerodrome USDC/USDT / Morpho Blue cards plus per-card error states. Tests: 9 unit (FastAPI endpoint + per-card failure paths + status-types guard + dashboard rendering + 10 s poll) plus a Playwright smoke that stubs the proxy and asserts all three cards render
- [x] Stand up audit-trail writer — `napg.audit` is the append-only SQLite log (one row per breach for now; decision/action kinds slot in via `record(kind, payload)` once substep 5 lands). Schema-level append-only triggers + per-row HMAC-SHA256 give two-layer tamper evidence. `napg audit verify` CLI verifies the chain end-to-end
- [x] Simulate a sequencer delay (mock RPC) and verify the migration path runs end-to-end on Sepolia — `napg.orchestrator.run_cycle` is the single decision-cycle entry point; `napg.scenarios.sequencer_delay_heartbeat` is the synthetic stale-block + reorg input. `napg simulate sequencer-delay [--execute]` runs the cycle on Sepolia (dry-run by default) and produces a scenario → breach... → decision → action audit chain that passes `napg audit verify`. Live Sepolia procedure: [manual test 1.9](docs/manual-tests/phase-1.md#19--simulated-sequencer-delay-end-to-end-pipeline)

### Security
- [x] All Web3.py providers use HTTPS only; reject `http://` at config-load time
- [x] Validate every RPC response against a Pydantic schema before acting on it (treat upstream as hostile)
- [x] Anthropic API key loaded via `pydantic-settings` from `.env`; logged as `***` only; never written to the audit DB — `napg.config.Settings.anthropic_api_key`; enforced by `test_audit_row_never_contains_the_api_key` and the equivalent test on the Reasoner
- [x] Per-provider rate-limit on RPC calls; circuit-break to a fallback RPC on repeated failure — `napg.monitor.resilience` ships a token-bucket `RateLimiter`, a consecutive-failure `CircuitBreaker` with half-open recovery, and a `FailoverRpcHeartbeat` that wraps N `RpcHeartbeat` instances with their own limiter+breaker pair. `Settings.active_rpc_urls()` returns `(primary, fallback?)` so the heartbeat CLI cuts over automatically when `BASE_SEPOLIA_RPC_URL_FALLBACK` is set; primary remains sticky to keep reorg history aligned
- [x] Testnet-only CDP wallet for Phase 1; cap balance to a known dust amount; document the address in the runbook — agent wallet is provisioned by `napg.wallet.build_agent_wallet` against the `NAPG_NETWORK=base-sepolia` configured CDP project. Address is captured in [manual test 1.6](docs/manual-tests/phase-1.md#16--simulated-sequencer-delay-end-to-end). MPC: keys never enter agent code, signing through CDP TEE only
- [x] Audit-log writes are wrapped in a single SQLite transaction per decision (no partial rows) — `record_breaches()` uses `with self._conn:` for all-or-nothing semantics
- [x] Add an HMAC column on each audit row signed with a separate key (cheap tamper-evidence; key in env, not DB) — `NAPG_AUDIT_HMAC_KEY` env var; key never written to the DB; live-verified in [manual test 1.7](docs/manual-tests/phase-1.md#17--audit-log-integrity)
- [x] Threat model: what happens if an RPC lies, if 0x returns crafted data, if Anthropic returns malformed JSON? Document the failure path for each — [docs/threat-models/phase-1.md](docs/threat-models/phase-1.md) walks each new surface (RPC, 0x, Anthropic, audit DB, wallet, prompt cache, secrets at rest), the mitigations in place, and the residual risks deferred to Phase 2 (AgentShield) or Phase 5 (mainnet cutover)

### Tests
- [x] Unit tests for each monitor (RPC, pool, lending) with mocked responses, >=80% coverage — `tests/monitor/test_rpc.py`, `test_aerodrome.py`, `test_morpho.py`, `test_resilience.py`; coverage 100/100/99/97% on the four monitor modules
- [x] Unit tests for breach-threshold evaluation — `tests/policy/test_breaches.py` (20 tests, `napg/policy/breaches.py` at 99%)
- [x] Integration test: full pipeline from mocked sequencer-delay event to a Sepolia testnet tx — mocked-pipeline half: `tests/test_orchestrator.py::test_sequencer_delay_drives_migrate_dispatch` and `::test_executed_migrate_records_tx_hash` cover scenario → breach evaluator → reasoner → action with a stubbed wallet returning a tx hash. Live Sepolia tx half lives in [manual test 1.9](docs/manual-tests/phase-1.md#19--simulated-sequencer-delay-end-to-end-pipeline)
- [x] Playwright smoke test on the dashboard route — `frontend/e2e/home.spec.ts` stubs `/api/status` and asserts the dashboard shell + all three cards render in Chromium
- [x] Audit-log test: every autonomous decision produces a recoverable record — `tests/test_orchestrator.py::test_audit_chain_ordering_breach_then_decision_then_action` asserts every cycle writes the `breach -> decision -> action` chain; `tests/test_audit.py::test_record_single_row_and_read_back` exercises the underlying writer
- [x] Tamper test: flipping a byte in an audit row fails HMAC verification — `tests/test_audit.py::test_verify_detects_tamper_after_triggers_dropped` (drops the append-only triggers, mutates a row, asserts `napg audit verify` flags it) plus `::test_update_blocked_by_trigger` and `::test_delete_blocked_by_trigger` for the schema-layer defence
- [ ] Manual test procedures completed: [docs/manual-tests/phase-1.md](docs/manual-tests/phase-1.md) — 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8 verified end to end (2026-05-18/19/20). 1.6 and 1.9 dry-run halves verified 2026-05-20; the live `--execute` halves of both stay blocked on a funded Base Sepolia wallet (`wallet show` reported `balance_wei: 0`)

### Success criteria
- [x] Dashboard renders live Sepolia data without errors — verified 2026-05-20 via `scripts/start.sh` against live Alchemy Base Sepolia + Base mainnet endpoints. Heartbeat reported block 41,735,849, Aerodrome quoted USDC/USDT at 0.99951 (5 bps, `Aerodrome_V3` in route), Morpho cards `WETH-USDC` and `cbBTC-USDC` both at 90.39 % utilisation. Auto-poll cadence, tab-visibility behaviour, per-card degrade, and console-error check additionally covered by `frontend/e2e/dashboard.spec.ts` (Playwright headless Chromium, all green)
- [ ] Agent detects the simulated sequencer delay and submits a migration tx on Sepolia
- [x] Audit log contains a complete, human-readable explanation for the migration — verified 2026-05-20 via 1.9 dry-run: the `decision` row records intent `migrate_to_safe`, confidence 0.97, `supporting_breaches=[reorg_is_breach, rpc_latency_ms_max, block_age_seconds_max]`, and a rationale that names the decision-matrix rules (2 reorg, 6 heartbeat degradation) and the threshold actuals (latency 4500/2000, block age 600/30) by name. Live `--execute` would replace `tx_hash: null` in the `action` row with the Sepolia receipt; the rationale itself is unchanged
- [ ] Phase 1 security checklist complete (schema validation, redaction, HMAC, threat model written)
- [ ] User signs off on Phase 1

### Troubleshooting
- **RPC heartbeat reports stale block height** -> provider lag or chain reorg -> cross-check against a second RPC; if both stale, mark provider degraded and switch fallback.
- **`web3.exceptions.TimeExhausted` on every call** -> provider throttling or down -> check provider status page, switch to fallback RPC, decrement rate-limit budget.
- **0x API returns empty pool list for USDC/USDbC** -> wrong `chainId` in request or unsupported pool -> confirm `chainId=8453` (mainnet) or `84532` (sepolia); verify pool address against Aerodrome's published list.
- **Seamless oracle freshness check always fails** -> price feed paused or oracle address changed -> compare against Seamless protocol docs; if confirmed paused, mark market degraded, do not migrate on stale-oracle alone.
- **Anthropic SDK returns HTTP 429** -> rate limit -> exponential backoff with jitter; persist last-good decision; alert if backoff >5 min.
- **Audit-log row missing `tx_hash` field** -> tx submitted but receipt poll timed out -> never delete the partial row; reconcile by tx hash in the next monitor cycle; log the reconciliation.
- **Sepolia faucet exhausted, wallet at zero** -> testnet wallet drained -> top up via Coinbase or Alchemy faucet; record the source in the runbook to track our test-funding pipeline.
- **Dashboard loads but shows no data** -> FastAPI endpoint returning 500 or CORS rejection -> hit endpoint directly with `curl`; check FastAPI logs; verify `next.config.ts` rewrites or CORS allowlist.
- **Tenderly simulation rejects a tx that succeeds onchain** -> simulation block stale -> set simulation block to `pending` or current head; re-run.

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

### Security
- [ ] Policy config file is signed (Ed25519 or similar); loader rejects unsigned or mismatched-signature configs
- [ ] Denylist source is a pinned hash or signed feed; reject stale (>24h without refresh) or unsigned lists
- [ ] Tenderly access key is scoped read-only; rotated when this phase ships
- [ ] Honeypot result cached per token, but cache invalidates when token contract `codeHash` changes
- [ ] **Kill-switch:** a single signed message (or env-var fallback) halts all signing within one decision cycle; tested
- [ ] `validate_or_die` is the only entry point to the wallet; CI grep test fails the build if any other code path calls `wallet.sign*`
- [ ] Phase 2 itself gets a written threat-model review: what bypasses exist, what we accept, what we fix later

### Tests
- [ ] Unit tests for each stage in isolation, >=80% coverage
- [ ] Integration test: a tx that fails policy is blocked and audit-logged
- [ ] Integration test: a known honeypot token fails Stage 4
- [ ] Negative test: removing any stage breaks the gate (validation is mandatory)
- [ ] Replay test: same input -> same decision (deterministic where it should be)
- [ ] Kill-switch test: engaging the switch blocks the next signing attempt within one cycle
- [ ] CI lint rule: no direct `wallet.sign*` calls outside `validate_or_die`
- [ ] Manual test procedures completed: [docs/manual-tests/phase-2.md](docs/manual-tests/phase-2.md)

### Success criteria
- [ ] Agent blocks a tx to a denylisted address
- [ ] Agent correctly fails the BUY-then-SELL honeypot probe on a known bad token
- [ ] No signing path bypasses `validate_or_die`
- [ ] Kill-switch verified end-to-end on Sepolia
- [ ] Phase 2 threat-model review filed
- [ ] User signs off on Phase 2

### Troubleshooting
- **All transactions blocked by policy** -> caps misconfigured or env mismatch -> diff `policy.toml` against the env's intended config; run the policy unit-test suite to surface the failing rule.
- **Tenderly simulation always reverts on a legit-looking tx** -> simulation context is stale or wrong chainId -> set simulation block to head, double-check `network_id`; reproduce with a known-good tx hash first.
- **Honeypot probe rejects a legit token** -> token has non-standard transfer hooks (rebasing, fee-on-transfer) -> capture the failure trace, evaluate as a manual review case; if accepted, allowlist with an audit-log note explaining why.
- **Kill-switch engaged but signing still happens** -> wallet code bypassed `validate_or_die` -> grep `wallet.sign`, `wallet.send`, `wallet.invoke` across the repo; refactor the offender; add a CI grep test to prevent regression.
- **Policy config loader fails: "signature mismatch"** -> config edited outside the signing flow -> re-sign with the policy admin key, commit, redeploy; never bypass the loader check.
- **Denylist refresh never updates** -> feed URL changed or auth expired -> hit feed URL directly, check auth, update env var; verify signature on the new list.

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

### Security
- [ ] SIWF signature verified server-side on every authenticated request; never trust the client's `fid` claim
- [ ] Strict CSP, no `unsafe-inline`; nonces for any required inline scripts
- [ ] Session cookies: `HttpOnly`, `Secure`, `SameSite=Lax`, narrowest `Domain` possible
- [ ] No session tokens, signed payloads, or wallet material in `localStorage` or `sessionStorage`
- [ ] CSRF token (double-submit cookie or origin check) on every state-changing API call
- [ ] Per-IP and per-fid rate-limits on `/api/auth/*` and `/api/agent/*`
- [ ] All API responses run through `redact()` before serialization; no internal addresses or keys leak
- [ ] Passkey-only for wallet ops; no mnemonic recovery path, period
- [ ] Subresource Integrity (SRI) hashes on any third-party scripts
- [ ] Lighthouse security pass and OWASP ZAP baseline scan; fix HIGH/CRITICAL before sign-off

### Tests
- [ ] Playwright e2e: SIWF login -> dashboard -> trigger a manual assurance check
- [ ] Wallet-creation test against CDP testnet
- [ ] Lighthouse pass on the dashboard (mobile) — perf + security categories
- [ ] OWASP ZAP baseline against the deployed staging URL
- [ ] Manual check inside the Base App in-app browser
- [ ] Manual test procedures completed: [docs/manual-tests/phase-3.md](docs/manual-tests/phase-3.md)

### Success criteria
- [ ] User can log in with Farcaster and see their Basename
- [ ] Passkey-backed MPC wallet is created with no seed phrase exposed
- [ ] App is discoverable inside the Base App mini-app directory
- [ ] CSP, cookie flags, and rate-limits verified in browser devtools
- [ ] ZAP baseline returns no HIGH/CRITICAL findings
- [ ] User signs off on Phase 3

### Troubleshooting
- **SIWF login loops; cookie never sets** -> third-party cookie blocking inside the Base App in-app browser -> use first-party cookies, confirm `Set-Cookie` domain matches the app's eTLD+1; check `SameSite` value.
- **Basename doesn't resolve, falls back to `0x...`** -> resolver cached a miss or RPC failed -> bypass cache, check resolver health, accept truncated-address fallback as graceful degrade.
- **Passkey prompt never fires** -> origin mismatch between manifest and deployed URL -> verify `manifest.json` `origin` and `relying_party_id` match the deployed domain exactly (including trailing slash).
- **EIP-5792 batch reverts on the second op** -> sponsored gas exhausted mid-batch or nonce conflict -> check paymaster balance, reduce batch size, ensure ops are nonce-independent.
- **CSP blocks a legitimate inline script** -> nonce not propagated -> generate nonce per-request in the layout, pass via header and script attribute.
- **Rate-limiter blocks the legitimate user** -> keying by IP behind a CDN -> key by `X-Forwarded-For`'s real client IP (validate CDN authenticity first) or by fid.
- **Mini-app doesn't show up in Base App directory** -> manifest validation failed -> hit `https://base.dev/manifest/validate` (or local validator), fix reported issues, resubmit.

## Phase 4 (Wk 5): Monetization and Attribution

Turn the agent into a revenue surface.

### Substeps
- [ ] Register Builder Code on Base.dev
- [ ] Suffix calldata on every NAPG-originated tx for ERC-8021 attribution
- [ ] Stand up x402 endpoints: agents pay USDC to receive an Assurance Report
- [ ] Define the Assurance Report schema (protocol, window, breaches, recommendation, signature)
- [ ] Implement Guardian Mode subscription scaffolding (no billing UI yet, just the entitlement check)
- [ ] Document the Native USDC treasury yield path on Base App (~3.35% APY baseline)

### Security
- [ ] x402 payment receipts verified as EIP-712 signed payloads; replay-protected with nonce + expiry
- [ ] Assurance Report payload signed with a **dedicated reporting key**, distinct from the operational wallet key
- [ ] Idempotency keys on every x402 endpoint: one payment = one report, even if retried
- [ ] Builder Code suffix is injected by a single calldata helper; never user-controllable; CI grep test enforces this
- [ ] Revenue accounting writes to the audit DB on every payment; reconcile against onchain receipts at the end of every billing period
- [ ] Subscription entitlement check uses the audit DB as source of truth, not client claims

### Tests
- [ ] On-chain check: a NAPG tx on Sepolia carries the correct Builder Code suffix
- [ ] x402 integration test: a paying client agent gets a signed Assurance Report; a non-paying one gets HTTP 402
- [ ] Replay test: re-sending the same x402 receipt is rejected
- [ ] Signature verification test: tampered Assurance Reports fail validation against the reporting public key
- [ ] Entitlement-check unit tests for Guardian Mode
- [ ] Manual test procedures completed: [docs/manual-tests/phase-4.md](docs/manual-tests/phase-4.md)

### Success criteria
- [ ] Builder Code registered and visible on Base.dev
- [ ] x402 endpoint produces a valid, signed Assurance Report on payment
- [ ] Replay and tamper tests both pass
- [ ] Revenue accounting reconciles to onchain receipts for a full test period
- [ ] User signs off on Phase 4

### Troubleshooting
- **x402 endpoint returns 402 forever, even with a valid payment** -> facilitator address misconfigured or wrong chain -> check the x402 server config; hit `/healthz` on the facilitator; verify the payment landed on the correct chain.
- **Builder Code missing from on-chain calldata** -> a tx-construction path bypassed the helper -> grep all call sites; refactor offenders; add CI test asserting the suffix is present on every NAPG-originated tx.
- **Assurance Report signature fails verification at the consumer** -> wrong key version or key rotated mid-report -> check key-rotation log; re-sign with the active key; publish the consumer-facing public key with a `kid` for future rotations.
- **Same payment delivered two reports** -> idempotency key missed or storage cleared -> persist idempotency keys with at least 30-day retention; reject duplicates at the API edge, not deep in the handler.
- **Revenue audit doesn't match onchain receipts** -> off-by-one in pagination or a missed event -> re-run the reconciliation from the last known-good block; never paper over the diff, find the missing event.

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

### Security
- [ ] All secrets in `fly secrets`; never baked into the Docker image; rotate every key as part of cutover
- [ ] Audit DB encrypted at rest (Fly volume encryption); daily encrypted backups to a separate bucket
- [ ] Restore-from-backup tested before launch, then monthly
- [ ] Key-rotation runbook written and rehearsed: ops wallet, reporting key, Anthropic, CDP, Tenderly
- [ ] Incident response plan: on-call paging contact, kill-switch authority, comms template, status-page update flow
- [ ] WAF / rate-limit on every public endpoint (Fly's edge or Cloudflare in front)
- [ ] CDN for static assets; origin shielded
- [ ] OWASP ZAP baseline (full, not just baseline) and a manual review of mainnet AgentShield policy before flipping live
- [ ] Status page transparently logs security incidents (with whatever delay is responsible)
- [ ] Mainnet AgentShield policy: tighter caps than testnet (per-tx, daily, weekly); reviewed in writing

### Tests
- [ ] Smoke run on mainnet with caps set to dust amounts
- [ ] Failover test: kill the agent, confirm monitors recover cleanly on restart
- [ ] Backup/restore test for the audit log (full restore, not just file copy)
- [ ] Kill-switch drill on mainnet
- [ ] Incident-response tabletop exercise
- [ ] Manual end-to-end: a real Base App user signs in, sees live data, opts into Guardian Mode
- [ ] Manual test procedures completed: [docs/manual-tests/phase-5.md](docs/manual-tests/phase-5.md)

### Success criteria
- [ ] Agent runs unattended on mainnet for 72 hours with no incidents
- [ ] First weekly Protocol Health Report is posted to Farcaster
- [ ] At least one external agent has paid via x402 for an Assurance Report
- [ ] Restore-from-backup and kill-switch drills both succeeded
- [ ] User signs off on launch

### Troubleshooting
- **Agent process restarts in a loop on Fly** -> OOM, audit DB write contention, or crashing on startup -> `fly logs`, check memory limit, profile DB writes; bump machine size only after profiling, not before.
- **Audit DB grows unbounded, disk near full** -> no archival policy -> implement monthly archive to cold storage; never truncate the live DB without an archived copy verified.
- **Mainnet tx repeatedly reverts** -> gas estimation stale, paymaster drained, or RPC selecting a bad fork -> check gas oracle, paymaster balance, switch RPC; if paymaster drained, fall back to user-pays gracefully.
- **False-positive breach migrates real funds** -> threshold too tight or oracle compromise -> engage kill-switch immediately; review audit log; tune threshold; consider rollback only via documented recovery path.
- **Backup restore produces a corrupt SQLite file** -> backup not consistent (e.g. mid-write copy) -> use `sqlite3 .backup` or LiteFS-style snapshotting, not `cp`; re-test.
- **Farcaster cast publishing fails silently** -> signer UUID rotated or Neynar quota hit -> check Neynar dashboard, refresh signer, re-queue; alert if queue depth >N.
- **Status page shows green but real users report breakage** -> health check too shallow -> deepen the check (synthetic transaction against a sentinel pool), not just a 200 on `/healthz`.
- **Kill-switch engaged but a tx still landed onchain** -> race between signing and switch propagation -> investigate which order; tighten switch propagation to <1 sec; document as a P0 incident regardless.

## Resolved decisions (2026-05-16)

- LLM provider: **direct Anthropic SDK** (Claude Opus-class). Keep prompt-caching first-class.
- Audit-log substrate: **SQLite from day one**. One table per concern, append-only writes.
- Production host: **Fly.io**. Dockerfile deploy, persistent volume for the audit DB.
- CI: **GitHub Actions wired up in Phase 0**. Lint + tests on every push from day one.
- Phase 1 monitoring targets:
  - Aerodrome: `USDC/USDT` Slipstream stable pool (originally `USDC/USDbC`; repointed 2026-05-19 after a live 0x probe showed USDbC has wound down — USDC/USDT Slipstream is now Aerodrome's deepest stable/stable pool and the surface a Protocol Service Assurance probe should actually be watching)
  - Morpho Blue (originally `Seamless: USDC, WETH, cbETH supply/borrow markets`; repointed 2026-05-19 because Seamless announced an orderly wind-down in April 2026 with the web app going offline 2026-06-30 — Coinbase Loans uses Morpho Blue on Base, making it the largest load-bearing lending surface NAPG could plausibly monitor). Probed markets: WETH-collateral → USDC loan (`0x8793...1bda`), cbBTC-collateral → USDC loan (`0x9103...1836`, the market that powers Coinbase Loans). Oracle-freshness half deferred to a follow-up substep because Morpho oracles are arbitrary `IOracle` contracts and need per-market introspection
