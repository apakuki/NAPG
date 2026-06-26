# NAPG Architecture — Developer Onboarding

This document gets a new developer up to speed on how NetAssure Protocol Guardian
(NAPG) is actually built, so you can extend it in any direction. It describes the
system as it exists in the repo, not the aspirational spec. Where the spec
([CLAUDE.md](../CLAUDE.md)) and the code diverge, the code wins and this document
follows the code.

Read [CLAUDE.md](../CLAUDE.md) for the project brief and hard constraints, and
[PLAN.md](../PLAN.md) for the phased build plan. This document is the map between
them and the source.

## 1. What NAPG does, in one paragraph

NAPG is a NOC-style service-assurance agent for the Coinbase Base ecosystem. It
runs **probes** against live infrastructure (an RPC heartbeat, an Aerodrome
USDC/USDT liquidity quote via the 0x API, and a Morpho Blue lending-market poll).
A rules engine turns those probe outputs into **Service Level Breach** records.
A **reasoning layer** (an Anthropic model called through tool-use) reads the
breaches and the raw state and decides one of three intents: `hold`,
`pause_for_investigation`, or `migrate_to_safe`. If the decision is to migrate
funds, the action is gated by **AgentShield**, a fail-closed 4-stage validation
pipeline, before any signature is requested from the MPC wallet. Every step of
every cycle is written to an append-only, HMAC-tamper-evident **audit log**. A
Next.js **frontend** renders the live monitor state and the breach history as a
Service Assurance Dashboard.

## 2. The mental model: one decision cycle

The whole agent is organised around a single function,
[`run_cycle`](../agent/napg/orchestrator.py), which executes one decision cycle
end to end. Everything else is either an input to that cycle or a service it
calls. The cycle is deliberately **probe-agnostic**: it receives already-collected
probe results rather than fetching them, which keeps I/O at the edges (the CLI
and the API) and makes the simulation path trivial.

```
            probes (live or synthetic)
                     |
        heartbeat / liquidity / morpho
                     |
                     v
        +---------------------------+
        | evaluate(thresholds, ...) |   napg/policy/breaches.py
        +---------------------------+
                     |  tuple[Breach, ...]
                     v
        +---------------------------+
        | reasoner.decide(inputs)   |   napg/reasoning.py  (Anthropic tool-use)
        +---------------------------+
                     |  Decision(intent, rationale, confidence, ...)
                     v
        intent == migrate_to_safe ?
                     |  yes
                     v
        +---------------------------+
        | migrate_to_safe(...)      |   napg/actions.py
        |   -> validator(intent)    |   napg/agentshield/  (4 stages, fail-closed)
        |   -> wallet.native_transfer
        +---------------------------+
                     |
                     v
              AuditLog (every step)      napg/audit.py
```

The audit chain produced per cycle is:

```
[scenario?] -> [breach...] -> [decision] -> [validation?] -> [action?]
```

- `scenario` lands only when a simulation drives the cycle (so a reader can tell
  a synthetic cycle apart from a live one).
- `breach` rows land only when the evaluator returns a non-empty tuple.
- `decision` always lands when a reasoner with an audit log decides.
- `validation` lands from inside AgentShield on every validation attempt, pass or
  fail.
- `action` lands only when the reasoner picks `migrate_to_safe` and the action
  runs.

If you understand that pipeline and the audit chain it emits, you understand the
agent. The rest is detail.

## 3. Repository layout

```
agent/                  Python 3.10+ agent core (uv toolchain)
  napg/
    __main__.py         CLI entry point: every operator action is a subcommand
    orchestrator.py     run_cycle — one decision cycle, end to end
    config.py           Settings (pydantic-settings, .env, HTTPS-only)
    reasoning.py        Reasoner — Anthropic tool-use decision layer
    actions.py          migrate_to_safe — the only onchain action (Phase 1)
    wallet.py           CDP MPC wallet bootstrap (the only CDP touch point)
    audit.py            append-only HMAC audit log
    redact.py           URL redaction (keys live in RPC URLs)
    scenarios.py        synthetic probe outputs for simulation
    api.py              FastAPI read endpoint powering the dashboard
    monitor/
      rpc.py            single-provider RPC heartbeat + reorg detection
      resilience.py     RateLimiter, CircuitBreaker, FailoverRpcHeartbeat
      aerodrome.py      0x-API liquidity probe (USDC/USDT peg)
      morpho.py         Morpho Blue lending-market poll
    policy/
      breaches.py       breach thresholds + evaluate() rules engine
    agentshield/
      pipeline.py       validate_or_die — 4-stage orchestration, fail-closed
      policy.py         signed policy/denylist config loaders (Ed25519)
      production.py     wire the four live stages from Settings
      stages/
        intent_judge.py   Stage 1 — independent Anthropic second opinion
        policy.py         Stage 2 — caps, allowlists, denylist, daily ceiling
        tenderly.py       Stage 3 — Tenderly simulation
        honeypot.py       Stage 4 — BUY-then-SELL honeypot probe (native: pass)
  config/               signed runtime config (policy.toml, denylist.toml, ...)
  tests/                pytest suite mirroring the package layout
  pyproject.toml        deps, ruff, pytest (coverage gate 80%)

frontend/               Next.js 16 App Router + Tailwind 4 (npm)
  src/
    proxy.ts            per-request CSP nonce (v16 "proxy" = old middleware)
    app/
      page.tsx          dashboard home
      api/              route handlers (status proxy, auth, audit, og images)
      _components/      React components (dashboard, breach feed, auth, wallet)
    lib/                session, siwf, csrf, redact, rate-limit, manifest, ...

docs/
  architecture.md       this file
  manual-tests/         per-phase manual test scripts
  threat-models/        per-phase threat models
  runbooks/             operational runbooks (branch protection, key acquisition)
  deploy-staging.md     Fly.io two-app deploy notes

scripts/                start.sh / stop.sh (run agent + frontend together)
```

## 4. The agent core

### 4.1 Configuration and secrets — `config.py`

[`Settings`](../agent/napg/config.py) is a `pydantic-settings` model and the
single source of truth for runtime config. It loads from `.env` (agent dir first,
then repo root). Two structural guarantees worth knowing:

- **HTTPS-only by construction.** A field validator rejects any RPC URL that does
  not start with `https://`, at load time. No monitor can accidentally point at a
  plaintext endpoint.
- **Network selector.** `NAPG_NETWORK` is `base-sepolia` (default) or
  `base-mainnet`. `active_rpc_urls()` returns `(primary, fallback?)` for the
  active network and raises if the primary is unset. Note that Aerodrome and
  Morpho live on Base **mainnet only**, so those probes always query mainnet
  regardless of `NAPG_NETWORK` — they read `BASE_RPC_URL` independently.

Secret material referenced by Settings: `ANTHROPIC_API_KEY`, `ZEROX_API_KEY`,
the three CDP secrets (`CDP_API_KEY_NAME`, `CDP_API_KEY_PRIVATE_KEY`,
`CDP_WALLET_SECRET`), `NAPG_AUDIT_HMAC_KEY`, and the three Tenderly slugs/keys.
See [.env.example](../.env.example) for the full set.

### 4.2 Monitors — `monitor/`

Every probe returns a frozen pydantic model. Upstream is treated as hostile: RPC
responses are validated through a model before anything acts on them.

- **RPC heartbeat** ([`rpc.py`](../agent/napg/monitor/rpc.py)). `RpcHeartbeat.tick()`
  measures round-trip latency, reads the latest block, and detects reorgs by
  checking that each new block's `parent_hash` chains to the block it previously
  recorded at `number - 1`. It keeps a small ring buffer of recent blocks. The
  `rpc_url` on the result is **redacted** (scheme + host only) via
  [`redact.py`](../agent/napg/redact.py) — managed RPCs embed API keys in the URL
  path, so the raw URL never enters a result object that could be logged.

- **Resilience primitives** ([`resilience.py`](../agent/napg/monitor/resilience.py)).
  A token-bucket `RateLimiter` and a `CircuitBreaker` (trips open after N
  consecutive failures, cools down, then half-opens). `gated_call(fn, limiter,
  breaker)` wraps a single call (breaker first, then limiter, then the call).
  `FailoverRpcHeartbeat` wires several `RpcHeartbeat` instances behind one
  `tick()`, each with its own limiter+breaker; the active provider is **sticky**
  so failover does not introduce spurious reorg signals from cross-provider hash
  drift.

- **Aerodrome liquidity** ([`aerodrome.py`](../agent/napg/monitor/aerodrome.py)).
  Queries the 0x v2 price endpoint for a USDC/USDT quote on Base mainnet
  (chainId 8453), computes `quoted_rate = buy_amount / sell_amount` and
  `peg_deviation_bps = round(abs(rate - 1.0) * 10_000)`, and records which
  sources filled. The probed pair is USDC/USDT (not USDbC, which wound down).

- **Morpho lending** ([`morpho.py`](../agent/napg/monitor/morpho.py)). Reads the
  `market(bytes32 id)` struct from the Morpho Blue singleton for two markets
  (WETH-USDC and cbBTC-USDC, the latter powering Coinbase Loans), computing
  utilisation in bps and how stale the on-chain accrual state is. Repointed from
  Seamless, which wound down.

All three accept an injected client (`Web3` / `httpx.Client`) so tests run without
network calls.

### 4.3 Breach evaluation — `policy/breaches.py`

[`evaluate(thresholds, heartbeat=, liquidity=, morpho=, now=)`](../agent/napg/policy/breaches.py)
is a pure function: it runs every applicable rule against whichever probe outputs
it is handed and returns a flat `tuple[Breach, ...]`. `now` is injectable for
deterministic tests.

`BreachThresholds` is the source of truth; [`config/breaches.toml`](../agent/config/breaches.toml)
mirrors its fields one-for-one and is loaded by `load_thresholds()`. Current rules:

| rule                          | source            | fires when |
|-------------------------------|-------------------|------------|
| `rpc_latency_ms_max`          | heartbeat         | latency > 2000 ms |
| `block_age_seconds_max`       | heartbeat         | latest block > 30 s old |
| `reorg_is_breach`             | heartbeat         | a reorg was detected |
| `peg_deviation_bps_max`       | aerodrome         | peg deviation > 50 bps |
| `liquidity_required`          | aerodrome         | 0x reports no liquidity |
| `market_utilization_bps_max`  | morpho:`<market>` | utilisation > 9500 bps |
| `market_staleness_seconds_max`| morpho:`<market>` | accrual state > 3600 s old |

Block-age uses `now - block.timestamp`, so a stale clock makes the agent *more*
suspicious, not less — the safe failure direction. A `Breach` is fully JSON-safe
(every field serialises) because it goes straight into the audit log.

### 4.4 Reasoning — `reasoning.py`

[`Reasoner.decide(inputs)`](../agent/napg/reasoning.py) calls the Anthropic SDK
directly (no LangChain, despite the spec table — a locked tech decision). Key
properties:

- **Structured output via tool-use.** The model is forced to call a single
  `submit_decision` tool with `intent`, `rationale`, `confidence`, and
  `supporting_breaches`. The result is parsed into a frozen `Decision` model.
- **Prompt caching.** The large system prompt (role + decision matrix + rationale
  quality rules) is marked `cache_control: ephemeral`. It is stable across calls,
  so cache reads accumulate. The per-tick state JSON is the uncached user message.
  `CacheMetadata` records token usage including cache creation/read.
- **The decision matrix lives in the system prompt.** This is where the agent's
  judgement is encoded as ordered rules (reorg => migrate; peg > 100 bps =>
  migrate; two simultaneous breaches across distinct sources => migrate; single
  soft breach => pause; etc.). If you want to change *how* NAPG decides, you edit
  `SYSTEM_PROMPT` here, not the rules engine (the rules engine decides *what is a
  breach*; the reasoner decides *what to do about breaches*).
- **Audit integration.** When given an `AuditLog`, every `decide()` writes one
  `decision` row. The Anthropic API key is never part of that row; a test enforces
  it.

The three intents: `hold` (no action), `migrate_to_safe` (move funds to the safe
contract — highest-cost action), `pause_for_investigation` (suspend autonomous
action without moving funds — a real product action, not a soft no).

### 4.5 Actions — `actions.py`

Phase 1 ships one action: [`migrate_to_safe`](../agent/napg/actions.py), a
native-ETH transfer from the CDP wallet to a pinned safe address. Critical
details:

- **Dry-run is the default.** A dry-run records an `action` row with
  `dry_run=True` and no tx hash; it never touches a wallet signing method.
- **Live calls require a validator.** A non-dry-run call *must* be given a
  `validator` callable (built by `build_production_validator`). The validator runs
  AgentShield's full pipeline *before any wallet method is touched* and raises
  `ValidationFailure` if any stage fails closed. The validation row already
  landed in the audit log inside `validate_or_die`, so a blocked tx still leaves a
  forensic trace even though no `action` row lands.
- **Wei vs ether gotcha.** `CdpEvmWalletProvider.native_transfer` expects whole
  ether (it runs `Web3.to_wei` internally), so the action divides wei by 10^18
  before calling. Passing wei would over-send by 10^18x and be rejected.
- **The wallet interface is a narrow `Protocol`** (`get_address`,
  `native_transfer`, `wait_for_transaction_receipt`) so tests inject a fake
  without the SDK.

### 4.6 The wallet — `wallet.py`

[`build_agent_wallet(settings)`](../agent/napg/wallet.py) is the **only** place
NAPG touches the CDP SDK. It returns a `CdpEvmWalletProvider`. MPC-only by
construction: keys live in CDP's TEE; the agent process never sees private keys,
mnemonics, or signed payloads. The only signing-control material the agent holds
is `CDP_WALLET_SECRET`, and it never lands in the audit DB.

### 4.7 The audit log — `audit.py`

[`AuditLog`](../agent/napg/audit.py) is an append-only SQLite table with two
layers of tamper defence:

1. **Append-only triggers.** SQLite `BEFORE UPDATE` / `BEFORE DELETE` triggers
   `RAISE(ABORT)`, so an operator running `UPDATE`/`DELETE` from `sqlite3` gets no
   changes.
2. **Row-level HMAC.** Each row carries an HMAC-SHA256 over
   `kind | recorded_at | payload`, keyed by `NAPG_AUDIT_HMAC_KEY`. If someone
   drops the triggers and edits rows, `verify()` detects the mismatch.

The HMAC key is never written to the DB and is treated as wallet-grade secret
material (a leaked key lets an attacker re-sign tampered rows). Rows are written
through `record(kind, payload)` (schema-agnostic beyond JSON-serialisability) or
`record_breaches()` (all-or-nothing for a set). `query()` and `iter_rows()` read
them back. `napg audit verify` recomputes every HMAC and reports tampered row ids.

The set of row kinds is open: today `scenario`, `breach`, `decision`,
`validation`, `action`. Add a kind by writing through `record()`.

### 4.8 AgentShield — `agentshield/`

This is the security gate between a decision and a signature. The orchestration
function is [`validate_or_die`](../agent/napg/agentshield/pipeline.py):

```
kill-switch -> Stage 1 Intent Judge -> Stage 2 Policy
            -> Stage 3 Tenderly -> Stage 4 Honeypot
```

- **Fail-closed.** First failing stage short-circuits; later stages do not run.
  A `ValidationFailure` carries the full `ValidationResult` so the caller can
  explain the block. Default stage callables raise `NotImplementedError`, so the
  pipeline refuses to validate until a real stage is injected.
- **Kill switch.** `NAPG_KILL_SWITCH=1` blocks all signing before any stage runs
  (Phase 5 swaps the env check for a signed-message variant behind the same API).
- **Every attempt is audited.** A `validation` row lands whether the pipeline
  passes, fails, or is kill-switched.
- **Stages are injectable callables** (`Callable[[TxIntent], StageResult]`), which
  is how each stage was landed independently and how tests stub them.

The `TxIntent` is the frozen contract every action declares before signing
(action, from/to, value, calldata, rationale, supporting breaches).

The four live stages:

1. **Intent Judge** ([`stages/intent_judge.py`](../agent/napg/agentshield/stages/intent_judge.py)).
   A *second, independent* Anthropic call (its own prompt + `submit_verdict`
   tool) that reviews the proposed action against its rationale and returns
   `agree` / `disagree` / `abstain`. Only `agree` passes — abstain is fail-closed,
   because uncertainty is not consent. Being a separate call means a
   prompt-injection on the reasoner does not also poison the judge.

2. **Policy** ([`stages/policy.py`](../agent/napg/agentshield/stages/policy.py)).
   Five checks in order: denylist, allowlist (when non-empty), per-tx value cap,
   calldata must be empty (native transfer only until ERC-20 decoding lands),
   and a rolling 24h daily-spend ceiling. This is the only stage that reads the
   audit log — it sums non-dry-run `action` rows in the trailing 24h for the
   daily ceiling.

3. **Tenderly** ([`stages/tenderly.py`](../agent/napg/agentshield/stages/tenderly.py)).
   POSTs the tx to Tenderly `/simulate` and fails closed if the simulation
   errored, the tx reverted, or gas-used is outside the native-transfer window.
   Detailed state-diff verification is deferred (documented as accepted risk in
   the Phase 2 threat model).

4. **Honeypot** ([`stages/honeypot.py`](../agent/napg/agentshield/stages/honeypot.py)).
   For token actions, a BUY-then-SELL probe. Phase 1's only action is a native
   ETH transfer, which has no target token, so this stage trivially passes for
   native transfers and fails closed for any non-native calldata (which Stage 2
   would already have blocked). A `HoneypotCache` keyed by `(address, codeHash)`
   is in place for the future token-aware path.

[`build_production_validator(settings, audit_log=)`](../agent/napg/agentshield/production.py)
composes all four live stages from `Settings` and returns the single validator
callable the action layer uses. It fails fast at boot if any required setting is
missing.

#### Signed config — `agentshield/policy.py`

The policy and denylist files are **Ed25519-signed**. The private key lives
outside the repo (`~/.napg/policy_signing_key.pem`); the public key is committed
at [`agent/config/policy_public_key.pem`](../agent/config/policy_public_key.pem).
The loader verifies the detached signature (`<file>.sig`) before parsing —
unsigned or mismatched configs are rejected. Workflow to change a policy value:
edit `policy.toml`, run `napg policy sign agent/config/policy.toml`, commit the
updated `.sig`. CLI helpers: `napg policy generate-key | sign | verify`.

### 4.9 The CLI — `__main__.py`

[`python -m napg`](../agent/napg/__main__.py) is how every operator action runs.
Each subcommand wires the live dependencies (Settings, wallet, audit DB,
Anthropic) so the library code stays I/O-free:

- `heartbeat` / `aerodrome` / `morpho` — run one probe, print the result JSON.
- `audit verify` — recompute HMACs.
- `wallet show` — print address, balance, network.
- `migrate --amount-eth X [--execute]` — dry-run (default) or live migration.
- `simulate sequencer-delay [--execute]` — synthesise a stale-block + reorg
  heartbeat (see [`scenarios.py`](../agent/napg/scenarios.py)) and run one full
  orchestrator cycle. This is the Phase 1 milestone path: agent detects a
  simulated sequencer delay and (with `--execute`) migrates testnet funds.
- `policy generate-key | sign | verify` — Ed25519 config signing.
- `serve [--host --port]` — run the FastAPI read endpoint via uvicorn.

### 4.10 The read API — `api.py`

[`create_app()`](../agent/napg/api.py) builds a small FastAPI app with three
endpoints:

- `GET /api/health` — liveness.
- `GET /api/status` — fans out the three probes in parallel (`asyncio.to_thread`,
  since they are blocking sync I/O) and returns one snapshot. **Each card is
  independent**: a probe that fails or whose env is unset returns a `CardError`
  for that card while the others still return data. The endpoint never
  partial-500s.
- `GET /api/audit/breaches?limit=&source=` — most recent `breach` rows from the
  audit log, reshaped for the UI (HMAC dropped), optionally filtered by source.

Each upstream (Aerodrome, Morpho) gets its own module-level limiter+breaker so a
flaky 0x does not trip the Morpho circuit. The API deliberately adds no CORS
middleware and binds 127.0.0.1 in dev — the production shape is the Next.js route
handler proxying server-side, so the browser never talks to this API directly.

## 5. The frontend

A Next.js 16 App Router app in [frontend/](../frontend/). Note
[frontend/AGENTS.md](../frontend/AGENTS.md): this Next.js version has breaking
changes from older training data; consult `node_modules/next/dist/docs/` before
writing frontend code.

### 5.1 How it connects to the agent

The browser only ever talks to the Next.js server. The route handler
[`src/app/api/status/route.ts`](../frontend/src/app/api/status/route.ts) proxies
server-side to the agent's FastAPI `/api/status` (address from `NAPG_API_URL`,
default `http://127.0.0.1:8000`), runs the response through a redaction pass, and
returns it. This side-steps CORS entirely and keeps the backend address off the
client.

### 5.2 Security model

- **CSP with per-request nonce.** [`src/proxy.ts`](../frontend/src/proxy.ts) (the
  v16 name for middleware) generates a fresh nonce per navigation and sets a
  nonce-based `Content-Security-Policy`. Static security headers (HSTS,
  X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy) live in
  `next.config.ts` `headers()` so they also cover static assets the proxy skips.
- **Sessions.** [`src/lib/session.ts`](../frontend/src/lib/session.ts) issues an
  HMAC-signed `napg_session` cookie (`HttpOnly`, `Secure` in prod, `SameSite=Lax`).
  Same HMAC pattern as the agent's audit log — deliberately rolling our own over
  pulling in a JWT library and its audit surface. The server re-verifies on every
  request and never trusts a client-supplied `fid`.
- **SIWF auth.** [`src/lib/siwf.ts`](../frontend/src/lib/siwf.ts) wraps
  `@farcaster/auth-client` for Sign In With Farcaster: create channel, poll,
  verify signature against the nonce we sent (replay defence). In-memory channel
  state is single-instance (fine for testnet; Phase 5 moves it to a shared store).
- **CSRF / rate limiting / redaction** live in `src/lib/` (`csrf.ts`,
  `rate-limit.ts`, `redact.ts`) and are unit-tested alongside their modules.

### 5.3 UI surface

[`page.tsx`](../frontend/src/app/page.tsx) renders the Service Assurance Dashboard
(`StatusDashboard` component, polling every 10 s). Other routes: `breaches/`
(breach feed), `protocols/[id]/` (per-protocol detail), `settings/`. Components
live in `src/app/_components/` (status dashboard, breach feed, passkey wallet,
sign-in/out, share-to-Farcaster). Mini-app discoverability is served via
`.well-known/farcaster.json` and per-page `fc:miniapp` embed metadata. Wallet
integration is wagmi/viem + Coinbase Wallet SDK (passkey smart wallet).

## 6. Running it locally

```bash
# one-time: copy and fill secrets
cp .env.example .env   # then edit

# agent
cd agent
uv sync
uv run pytest                 # full suite, coverage gate 80%
uv run python -m napg heartbeat
uv run python -m napg simulate sequencer-delay        # dry-run end-to-end cycle

# frontend
cd ../frontend
npm install
npm run dev                   # http://localhost:3000

# both together
./scripts/start.sh            # agent uvicorn :8000 + frontend :3000
./scripts/stop.sh
```

Quality gates mirror CI ([.github/workflows/ci.yml](../.github/workflows/ci.yml)):
`uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` (agent);
`npm run lint`, `npm run test`, `npm run build` (frontend); plus pip-audit,
npm audit, and a gitleaks scan.

## 7. Extension recipes

The architecture is built to be extended along a few well-defined seams. Each
recipe below is the minimal-surprise path.

### 7.1 Add a new monitor (probe)

1. Create `agent/napg/monitor/<name>.py` with a frozen pydantic result model and
   a `Monitor` class whose `tick()` returns it. Inject the client (`Web3` /
   `httpx.Client`) so tests can mock it. Gate outbound calls with `gated_call`
   (or a limiter+breaker) from [`resilience.py`](../agent/napg/monitor/resilience.py).
   Redact any key-bearing URL via [`redact.py`](../agent/napg/redact.py).
2. Add the result type as an optional input to
   [`evaluate()`](../agent/napg/policy/breaches.py) and write an `_eval_<name>`
   helper that emits `Breach` records. Add the matching thresholds to
   `BreachThresholds` and `config/breaches.toml`.
3. Thread the probe through wherever cycles are driven: add an optional field to
   `ReasoningInputs`, pass it into `run_cycle`, and surface it in the system
   prompt's decision matrix if it should influence decisions.
4. Expose it on the dashboard: add a card to `StatusResponse` in
   [`api.py`](../agent/napg/api.py) with its own limiter+breaker, then render it
   in the frontend status dashboard.
5. Add a CLI subcommand in [`__main__.py`](../agent/napg/__main__.py) and tests
   under `agent/tests/monitor/`.

### 7.2 Add a breach rule

Add a field to `BreachThresholds`, mirror it in
[`config/breaches.toml`](../agent/config/breaches.toml), emit the `Breach` from
the relevant `_eval_*` helper, and add a row to the table in section 4.3. If the
rule should change *behaviour*, add a clause to the decision matrix in
[`reasoning.py`](../agent/napg/reasoning.py)'s `SYSTEM_PROMPT`.

### 7.3 Add an onchain action

1. Write the action in [`actions.py`](../agent/napg/actions.py) following
   `migrate_to_safe`: validate inputs, default to dry-run, require a `validator`
   for live calls, build a `TxIntent`, call `validator(intent)` *before* any
   wallet method, and record an `ActionRecord` to the audit log.
2. Add the intent to the reasoner's `Intent` literal, `submit_decision` tool
   schema, and decision matrix.
3. Dispatch it from [`run_cycle`](../agent/napg/orchestrator.py).
4. **Do not call wallet signing methods anywhere outside `napg.actions` or
   `napg.agentshield`** — a CI invariant test
   ([`test_codebase_invariants.py`](../agent/tests/test_codebase_invariants.py))
   greps for `native_transfer`, `send_transaction`, `invoke`, `sign_message`,
   `sign_typed_data`, `wait_for_transaction_receipt` and fails the build if they
   appear elsewhere. This is the structural guarantee that every signature routes
   through `validate_or_die`.

### 7.4 Add or refine an AgentShield stage

Stages are `Callable[[TxIntent], StageResult]`. To add a real BUY-then-SELL
honeypot path or ERC-20 calldata decoding, implement the stage in
`agentshield/stages/`, wire it in
[`production.py`](../agent/napg/agentshield/production.py), and keep it
fail-closed (return `StageResult(passed=False, ...)` on any doubt). The pipeline
order and audit emission are fixed in
[`pipeline.py`](../agent/napg/agentshield/pipeline.py); you should not need to
touch it to add stage logic.

### 7.5 Add a frontend card or route

Add a route handler under `src/app/api/` that proxies server-side (never expose
the agent address to the browser), a component under `src/app/_components/`, and
co-locate a `*.test.tsx`. Respect the CSP — inline scripts/styles need the nonce
from `proxy.ts`. Add a Playwright spec under `e2e/` for the navigation path.

## 8. Conventions and invariants to respect

- **No emojis anywhere** — code, commits, UI, docs. Hard constraint.
- **Keep it simple.** No defensive programming, no speculative features. Three
  lines beats a premature abstraction. Stages and probes accept injected clients
  rather than growing their own config surface.
- **Every autonomous decision must be audit-recoverable.** If you add a step that
  influences a decision or an action, write it to the audit log via a typed,
  JSON-safe payload.
- **Fail closed.** Security stages, the kill switch, and unconfigured probes all
  default to the safe outcome (block / error card), never the permissive one.
- **Secrets never enter results or the audit DB.** URLs are redacted at the
  monitor boundary; API keys and the wallet secret are never serialised into any
  row (tests enforce this for the audit log).
- **80% coverage gate** on the agent (`--cov-fail-under=80` in
  [`pyproject.toml`](../agent/pyproject.toml)). New modules need tests mirroring
  the package layout under `agent/tests/`.
- **Frontend Next.js is non-standard** — read the bundled docs in
  `node_modules/next/dist/docs/` before writing route handlers, proxy logic, or
  metadata.

## 9. Where to look next

- [PLAN.md](../PLAN.md) — the phased plan with success criteria; the authoritative
  record of what is built vs deferred per phase.
- [docs/threat-models/](threat-models/) — per-phase threat models, including the
  accepted risks (e.g. Tenderly state-diff deferral).
- [docs/manual-tests/](manual-tests/) — per-phase manual test scripts that
  exercise the live system.
- [docs/deploy-staging.md](deploy-staging.md) — the Fly.io two-app deploy (private
  agent + public frontend), including the IPv6 6PN bind gotcha.
</content>
</invoke>
