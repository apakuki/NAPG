# System security plan: NAPG (NetAssure Protocol Guardian)

| | |
|---|---|
| Version | 0.1 draft, 14 October 2026 |
| System owner | Samuel Nayacakalou |
| Classification of information handled | None (public infrastructure data, testnet funds) |
| Environment assessed | Developer workstation, GitHub repository and CI, Fly.io staging (Sydney region) |
| Controls annex | [control-mapping.md](control-mapping.md) |
| Residual risks | [risk-register.md](risk-register.md) |

This plan meets the structure ISM-0041 asks for: an overview of the system's purpose, boundary and management, with the applicable controls in an annex.

## 1. Purpose

NAPG is an AI monitoring agent that applies network operations centre (NOC) service-assurance practice to blockchain infrastructure on the Base network. It:

- runs probes against RPC endpoints and two decentralised-finance protocols (a liquidity pool and a lending market);
- turns probe results into Service Level Breach records against fixed thresholds;
- asks an AI reasoning layer to choose one of three responses: hold, pause for investigation, or move funds to a pre-defined safe address;
- gates any fund movement through a four-stage, fail-closed validation pipeline (AgentShield) before a signature is requested;
- records every step in an append-only, tamper-evident audit log;
- shows live status and breach history on a web dashboard.

The only action that changes anything outside the system is a transfer from the agent's wallet to a fixed safe address. Today that wallet holds testnet funds only.

## 2. System boundary

### In scope

| Component | Where it runs | Role |
|---|---|---|
| Agent core (`agent/napg/`) | Fly.io app `napg-agent-staging`, private network only, no public address | Probes, breach rules, reasoning, AgentShield, actions, audit log, read API |
| Audit database (SQLite) | Fly.io persistent volume at `/data` | Append-only record of every decision cycle |
| Frontend (`frontend/`) | Fly.io app `napg-frontend-staging`, public over HTTPS | Dashboard, breach feed, sign-in, server-side proxy to the agent |
| Signed configuration (`agent/config/`) | Repository, loaded at agent start | Value caps, allow and deny lists, breach thresholds |
| Source repository and CI | GitHub (`apakuki/NAPG`, public), GitHub Actions | Authoritative source for software; build, test and security scans |
| Operator workstation | Owner's macOS laptop | Development, policy signing key, local secrets |

### Out of scope (external services the system depends on)

Coinbase Developer Platform (wallet keys and signing in a trusted execution environment), the Base network, Anthropic (AI models), Tenderly (transaction simulation), 0x (price quotes), the Farcaster sign-in relay, and Fly.io's platform. Each is listed with its criticality and exit plan in the [dependency register](../dependency-register.md). The system treats all of them as untrusted at the boundary: responses are parsed into strict schemas before use.

### Data flows

```
Internet probes (RPC, 0x, lending market)
        |  HTTPS only, rate-limited, circuit-broken, schema-validated
        v
+-------------------- Fly.io private network (6PN) ---------------------+
|  Agent: breach rules -> AI reasoner -> AgentShield (4 stages) -> action  |
|         every step -> audit log (SQLite, HMAC rows, append-only)        |
|  Read API :8080 (internal only)                                         |
+------------------------------------------------------------------------+
        ^  server-side proxy, responses redacted
        |
Frontend (public HTTPS, CSP with nonce, HSTS, signed session cookie)
        ^
Browser (untrusted)

AgentShield stage calls out to: Anthropic (Intent Judge), Tenderly (simulation)
Action calls out to: Coinbase Developer Platform (signing), Base network
```

The browser never talks to the agent directly. The agent has no public endpoint. Secrets for the staging apps are held in Fly.io secrets, not in images.

## 3. How the system is managed

| Function | How it is done | Evidence |
|---|---|---|
| Ownership and approval | One person owns, develops, operates and approves changes. There is no separation of duties (see risk R03). | This plan |
| Change control | All change through the GitHub repository. Changes to `main` go through a pull request, and a ruleset requires CI to pass lint, tests (80% coverage floor), dependency audits and a secret scan; force-push and deletion are blocked. Policy changes require a fresh Ed25519 signature. | `.github/workflows/ci.yml`, [architecture.md 4.8](../architecture.md) |
| Dependency updates | Dependabot raises weekly pull requests for Python, npm and GitHub Actions. Unpatchable advisories are allow-listed in CI with a written reason. | `.github/dependabot.yml`, `ci.yml` pip-audit step |
| Secrets | Staging: Fly.io secrets. Development: `.env` and key files on the workstation, excluded from git and scanned for by gitleaks. | `.gitignore`, `.pre-commit-config.yaml`, [deploy-staging.md](../deploy-staging.md) |
| Monitoring | The audit log records every breach, decision, validation and action. `napg audit verify` checks every row's HMAC. | `agent/napg/audit.py` |
| Incident handling | Runbooks for key compromise, kill switch, infrastructure outage, emergency migration and false positives. No consolidated incident response plan yet (risk R10). | [runbooks/](../runbooks/) |
| Emergency stop | `NAPG_KILL_SWITCH=1` blocks all signing before any validation stage runs. | [runbooks/kill-switch.md](../runbooks/kill-switch.md) |

## 4. Security objectives

1. **Fail closed.** Any doubt, missing configuration, unavailable dependency or failed check results in no action.
2. **No fund movement without validation.** Every signature passes AgentShield; a CI test fails the build if signing methods are called anywhere else.
3. **Every autonomous decision is recoverable.** Each cycle leaves a complete, tamper-evident record of what was seen, decided, checked and done.
4. **Secrets never enter logs or responses.** URLs are redacted at the probe boundary; tests assert keys never appear in audit rows; frontend responses pass a second redaction step.
5. **Bounded blast radius.** Per-transaction value cap, rolling 24-hour spend ceiling, fixed safe address, and a maximum acceptable permanent loss of 5% set in the [treasury policy](../treasury-policy.md).

## 5. AI system card (ISM-2084)

| Item | Detail |
|---|---|
| Models | An Anthropic Claude model as the reasoner (identifier recorded on every decision row) and a different Claude model as the AgentShield Intent Judge |
| Use | Choose a response to detected breaches; independently review any proposed transfer |
| Inputs | Breach records and validated probe state as JSON. No personal data. No user-supplied prompts. |
| Outputs | A structured decision through a single forced tool call: intent, rationale, confidence, supporting breaches |
| Authority | None directly. The model cannot call the wallet. A decision to move funds is only a request that AgentShield then validates. |
| Known risks | Prompt injection through manipulated protocol state; plausible but wrong rationale; vendor outage |
| Mitigations | Independent second model with its own prompt and tool schema; deterministic policy stage; simulation stage; value caps; kill switch; fail-safe on outage (no decision means no action) |
| Training | Organisational data is not used to train models (API use only) |
| Confidence scores | Recorded in the audit log only; not exposed in the dashboard or the public API (ISM-2085) |

## 6. AI agent register entry (ISM-2134, ISM-2135)

| Field | Value |
|---|---|
| Unique identifier | `napg-agent-staging` |
| Owner and business purpose | Samuel Nayacakalou; automated service assurance for monitored protocols |
| Identities assigned | A dedicated Coinbase Developer Platform wallet (keys held by Coinbase, never by the agent); dedicated API keys for Anthropic, 0x and Tenderly |
| User accounts and credentials used | No human user accounts. Secrets: `ANTHROPIC_API_KEY`, `ZEROX_API_KEY`, `CDP_API_KEY_NAME`, `CDP_API_KEY_PRIVATE_KEY`, `CDP_WALLET_SECRET`, `NAPG_AUDIT_HMAC_KEY`, Tenderly access key |
| Tools and permissions | Reasoner: one tool (`submit_decision`), no execution rights. Code path: read-only probes; one action (`migrate_to_safe`) to a single pinned address, only after AgentShield passes |
| Data repositories accessed | Its own audit database; public RPC and API data |
| Last verified | 14 October 2026 |

## 7. Residual risk summary

The highest-rated residual risks are listed in full in the [risk register](risk-register.md):

- R01: autonomous fund movement without human approval (deviation from ISM-2113), accepted for testnet with compensating controls and a mainnet gate.
- R03: no independent review of code or security changes.
- R04: long-lived secrets held as plain files on the operator workstation.

## 8. Document control

Review this plan at each phase sign-off, on any new external dependency, and before the Phase 5 mainnet cutover. The mainnet review must re-assess R01 with the owner's written decision.
