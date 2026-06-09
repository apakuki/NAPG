# Phase 0 threat model — scaffolding layer

Scope: the local development environment only. No production attack surface exists yet — no deployed services, no live wallet, no network endpoints accepting traffic.

This document is the written threat-model delta required by [PLAN.md](../../PLAN.md#cross-cutting-security-baseline) for Phase 0 sign-off. Each subsequent phase appends its own file under `docs/threat-models/`.

## In scope

- The contributor's dev box (where `uv sync` and `npm install` run).
- The GitHub repository (source, CI workflows, settings).
- The CI runners (GitHub Actions, ephemeral).

## Out of scope

- Production hosts (none yet — lands in Phase 5).
- Mainnet wallets (none — testnet wallet doesn't land until Phase 1).
- End users of the dashboard (no public deployment).

## Assets

- Source code under `main`.
- `.env.example` (no secrets, only key names).
- CI configuration in `.github/workflows/`.
- Dependency manifests (`pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`).

There are no secrets, signing keys, or production credentials in scope this phase. `.env` is local-only and gitignored; `docs/manual-tests/phase-0.md` step 0.6 verifies the ignore rule holds.

## Threats and mitigations

| Threat | Mitigation |
|---|---|
| Secret accidentally committed to git | `.gitignore` excludes `.env*`; gitleaks pre-commit hook (`.pre-commit-config.yaml`); gitleaks CI scan re-checks every push |
| Vulnerable transitive dependency | `pip-audit` (agent) and `npm audit --audit-level=high` (frontend) run in CI; Dependabot opens PRs weekly for uv, npm, and github-actions ecosystems |
| Supply-chain attack via build tooling | Lockfiles (`uv.lock`, `package-lock.json`) committed; CI uses `uv sync` and `npm ci` which honour lock pins |
| CI workflow tampered with via PR | Branch protection on `main` can require CI green and reviewed merges; briefly enabled 2026-06-02 then removed when the project returned to a single maintainer (a review gate is unsatisfiable solo). Re-enable if a collaborator joins; see Accepted risks |
| Stale or compromised GitHub Action | Dependabot updates the `github-actions` ecosystem weekly; actions are pinned to major-version tags |
| Compromised contributor workstation | Out of scope for code mitigations; relies on contributor security hygiene |

## Accepted risks

- No reproducible builds yet (Docker image work lands in Phase 5).
- No SBOM published yet (will revisit at Phase 5 cutover).
- Pre-commit hooks are opt-in — contributors must run `pre-commit install` once. The CI gitleaks job is the backstop for anyone who skipped that step.
- Branch protection on `main` is not currently enabled (original deferral recorded 2026-05-17). GitHub's branch-protection and ruleset APIs require GitHub Pro (or a public repo) for this private repo; `apakuki` is on Pro, so a ruleset is technically available. A ruleset was briefly enabled 2026-06-02 and then removed when the project returned to a single maintainer: solo-dev mode means the only attacker is the maintainer's own machine (covered by workstation hygiene), and a required-review gate cannot be satisfied by a sole maintainer (no self-approval). Re-enable triggers: (a) another collaborator joins, (b) the repo goes public, or (c) Phase 5 mainnet cutover — whichever comes first. Re-enable steps are in [docs/runbooks/branch-protection.md](../runbooks/branch-protection.md).

## Next phase delta

Phase 1 will add: a testnet wallet (treated as low-value but kept in MPC), a SQLite audit log (append-only, HMAC-signed), an Anthropic API key (loaded from `.env`, redacted from logs), and outbound RPC calls (HTTPS-only, rate-limited). Each gets its own row in the Phase 1 threat-model file.
