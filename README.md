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

## Status

Greenfield, Phase 0 (scaffolding). See [PLAN.md](PLAN.md) for what is and isn't built yet.
