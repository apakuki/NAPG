# NAPG — NetAssure Protocol Guardian

Autonomous AI agent providing NOC-level Protocol Service Assurance for decentralized protocols on the Coinbase Base ecosystem. Heartbeats RPC nodes, monitors sequencer latency and liquidity-pool health, detects Service Level Breaches, and can autonomously migrate funds to a pre-defined safe state.

See [CLAUDE.md](CLAUDE.md) for the project brief and [PLAN.md](PLAN.md) for the phased build plan.

## Layout

- `agent/` — Python 3.10+ agent core (monitoring, reasoning, execution, security, audit log)
- `frontend/` — Next.js + Tailwind app (Service Assurance Dashboard, mini-app for Base App)
- `scripts/` — start/stop helpers
- `.github/workflows/` — CI

## Running locally

Prerequisites: `uv` (Python), Node.js 20+, Docker (optional).

```bash
# Agent
cd agent
uv sync
uv run pytest

# Frontend
cd frontend
npm install
npm run dev
```

Copy `.env.example` to `.env` and fill in keys before running the agent against any network.

## Security

Security is built into each layer as it lands rather than added at the end:

- **AgentShield** 4-stage validation before any signature: Intent Judge, Policy Validation, Tenderly simulation, honeypot detection
- **Tamper-evident audit log**: append-only SQLite with per-row HMAC-SHA256 chaining; `napg audit verify` checks the chain end to end
- **Signed policy files** and a **kill switch** that halts all signing immediately
- **Supply chain**: gitleaks secrets scanning (pre-commit and CI), `pip-audit` and `npm audit` in CI, Dependabot, with accepted advisories documented in CI
- **Threat models** per phase in [docs/threat-models/](docs/threat-models/) and incident runbooks in [docs/runbooks/](docs/runbooks/)

See [SECURITY.md](SECURITY.md) for the disclosure policy.

## Status

Running on Base Sepolia testnet only; no mainnet deployment.

- Phases 1-2 complete: monitoring core, reasoning layer, AgentShield security layer, audit log, end-to-end simulated sequencer-delay migration verified on Sepolia
- Phase 3 complete (one item open): Service Assurance Dashboard and Base App mini-app
- Phase 4 in progress: monetisation and attribution
- Phase 5 not started: validation, operational readiness and mainnet launch

See [PLAN.md](PLAN.md) for the full checklist.
