# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: NetAssure Protocol Guardian (NAPG)

NAPG is an autonomous AI agent providing Network Operations Center (NOC) level **Protocol Service Assurance** for decentralized protocols on the Coinbase Base ecosystem (Ethereum L2, OP Stack). It heartbeats RPC nodes, monitors sequencer latency and liquidity-pool health, detects "Service Level Breaches" (peg drops, transaction-revert spikes, honeypot signatures), and can autonomously migrate funds to a pre-defined safe state.

Positioning: the reliability layer the Base ecosystem currently lacks — institutional-grade DeFi assurance built with federal-grade security rigor. See [Building on Coinbase Base Ecosystem.pdf](Building on Coinbase Base Ecosystem.pdf) for the authoritative brief.

## Builder profile

Samuel Apakuki Nayacakalou ([linkedin.pdf](linkedin.pdf), [github.com/apakuki](https://github.com/apakuki)). 17.5 years at Optus as a Tier 1 Technical Analyst providing 24x7 service assurance to Federal Government clients — Cisco routing/switching, telephony, Unified Communications, with Moogsoft/StatSeeker/HP Openview for monitoring. Federal Government cleared. Self-taught Python developer since 2019; built a crypto trading bot that ran 1.4% daily compounded over 60,000 trades. UoS FinTech Bootcamp 2022–23, Postgrad Internetworking (UTS), BSc Computer Science (Curtin).

NAPG is the deliberate translation of that skill set onto Base: SLA-driven service assurance → onchain Protocol Service Assurance; Cisco troubleshooting → transaction-path auditing; Moogsoft/StatSeeker heartbeating → Web3.py RPC monitoring; Python trading-bot algorithmic maturity → autonomous agent orchestration.

## Project status

Greenfield. Repo currently contains only the spec PDF and supporting docs — no application code yet.

## Architecture (per the brief)

| Layer       | Component                              | Function                                                                |
|-------------|----------------------------------------|-------------------------------------------------------------------------|
| Reasoning   | LangChain + Claude (Opus-class)        | Interpret natural-language commands and protocol-state data            |
| Execution   | CDP AgentKit (Python)                  | Onchain actions: swaps, transfers, contract deployments                 |
| Monitoring  | Web3.py + AgentiPy                     | Heartbeat RPC nodes, analyze pool liquidity via 0x API                  |
| Security    | AgentShield policy engine              | Per-tx caps, allowlists, honeypot detection, Tenderly simulation        |
| Payment     | x402 protocol (HTTP 402)               | Agent-to-agent USDC micro-payments for service data                     |
| Frontend    | Next.js + Tailwind CSS                 | Standard Web App optimized for Base App in-app browser                  |
| Identity    | SIWF + Basenames (BNS)                 | No-password auth via Farcaster / human-readable wallet names            |
| Wallet      | CDP MPC Smart Wallet (Passkey)         | Keys isolated in TEE; sponsored gas + EIP-5792 batch transactions       |
| Attribution | Builder Code (ERC-8021)                | Calldata suffixing for sequencer reward eligibility                     |

## Hard constraints

- **Python 3.10+** for agent core; **Next.js** frontend in a `frontend/` subdirectory.
- **MPC wallets only** — private keys never touch agent code directly; all signing through CDP TEE.
- **AgentShield 4-stage validation** before any signature: Intent Judge → Policy Validation → Tenderly Simulation → Honeypot Detection (BUY-then-SELL test).
- **Permanent audit trail** for every autonomous decision (the "why" must be recoverable for compliance review).
- **No emojis anywhere** — code, commits, README, UI. Not negotiable.
- Keep it simple: no defensive programming, no speculative features, no over-engineering. Three lines beats a premature abstraction.

## Roadmap (6-week rapid launch)

1. **Phase 1 (Wk 1–2) — Prototype & Logic Core.** Python monitoring scripts + Service Assurance Dashboard heartbeating Aerodrome, Seamless on Base Sepolia. Milestone: agent detects simulated sequencer delay and moves testnet funds to safe contract.
2. **Phase 2 (Wk 3) — Security Layer.** Integrate AgentShield 4-stage pipeline. Milestone: agent blocks denylist tx and fails honeypot simulation correctly.
3. **Phase 3 (Wk 4) — Frontend & Social Distribution.** Next.js app, SIWF auth, Base.dev metadata, discoverable in Base App mini-app directory.
4. **Phase 4 (Wk 5) — Monetization & Attribution.** Register Builder Code on Base.dev for ERC-8021 attribution; wire up x402 for agent-to-agent payments.
5. **Phase 5 (Wk 6) — Mainnet Launch.** Deploy to production host, start Cast-Driven Onboarding Loop on Farcaster, weekly Protocol Health Reports.

## Monetization model

- ERC-8021 Builder Code rewards (calldata suffix → sequencer reward share).
- x402 micro-payments (USDC) for other agents requesting Assurance Reports.
- B2C "Guardian Mode" subscriptions (monitor specific lending/LP positions, push Base Dashboard notifications).
- Native USDC treasury yield on Base App (~3.35% APY baseline).

## Workflow expected by the spec

1. Write a phased plan with success criteria (scaffolding, `.gitignore`, unit tests included) before executing.
2. Execute against the plan, checking criteria off.
3. Integration test with Playwright (frontend) and testnet runs (agent); fix defects.
4. "Done" means MVP complete, tested, with the agent live on testnet or mainnet per the current phase.

## Library choices

Use latest stable versions and idiomatic patterns as of the current date. Prefer popular, well-maintained libraries (`coinbase-agentkit`, `web3.py`, `agentipy`, `wagmi`, `viem`, `@dnd-kit/*` only if drag-drop ever lands) over hand-rolled alternatives.

## Commands

None yet — neither the Python agent nor the Next.js frontend has been scaffolded. Once they exist, standard tooling applies:
- Agent (root or `agent/`): `python -m pytest`, `python -m napg ...` (TBD).
- Frontend (`frontend/`): `npm run dev` / `build` / `lint` / `test`.

Update this section when scaffolding lands.
