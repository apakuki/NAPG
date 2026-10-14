# Control mapping: ISM controls applied to NAPG

Annex to the [system security plan](system-security-plan.md). Control identifiers and wording come from the ISM September 2026 release (OSCAL `v2026.09.4`). Requirement text is shortened; read the ISM for the full statement.

**Status key:** Implemented · Partial · Not implemented · Inherited (met by a provider) · To confirm (depends on account settings outside the repository) · N/A (not applicable to this system)

## Summary

Counted by row. Some rows cover two closely related controls, so the 64 rows below cover 74 ISM controls.

| Area | Implemented | Partial | Not implemented | Inherited or to confirm | N/A |
|---|---|---|---|---|---|
| Security documentation and incidents | 1 | 3 | 1 | 0 | 0 |
| Software development | 11 | 10 | 2 | 0 | 0 |
| Web application development | 3 | 2 | 1 | 0 | 0 |
| AI application development | 7 | 3 | 2 | 0 | 1 |
| System access and credentials | 1 | 2 | 0 | 0 | 0 |
| Security monitoring and event logging | 2 | 3 | 2 | 0 | 0 |
| Backups, supply chain and cryptography | 2 | 2 | 1 | 1 | 1 |
| **Total (64 rows)** | **27** | **25** | **9** | **1** | **2** |

## 1. Security documentation and incidents

| Control | Requirement (short) | Status | How NAPG meets it | Evidence |
|---|---|---|---|---|
| ISM-0041 | System security plan with overview and controls annex | Implemented | This package | [system-security-plan.md](system-security-plan.md) |
| ISM-0043 | Incident response plan covering incident types, reporting, authority and criteria | Partial | Five scenario runbooks exist; no single plan defining incident types, reporting paths and authority. The kill-switch authority is an open decision. | [runbooks/](../runbooks/), [kill-switch.md](../runbooks/kill-switch.md) "Authority: open decision" |
| ISM-0912 | Change and configuration management plan | Partial | Baselines held as signed config and lockfiles; changes go through git and CI. No written plan defining routine vs urgent changes, approvers or notification. | [architecture.md 4.8](../architecture.md), `ci.yml` |
| ISM-0125 | Cyber security incident register | Not implemented | The audit log records system events, not security incidents. | Risk R10 |
| ISM-1526 | System owner monitors security, threats, risks and controls | Partial | Per-phase threat models, dependency register and this package. A sole owner reviews their own work. | [threat-models/](../threat-models/), [dependency-register.md](../dependency-register.md) |

## 2. Software development

| Control | Requirement (short) | Status | How NAPG meets it | Evidence |
|---|---|---|---|---|
| ISM-2120 | Secure software development policy | Partial | The cross-cutting security baseline in PLAN.md and the conventions in architecture.md act as the policy; not issued as a standalone policy. | `PLAN.md` "Cross-cutting security baseline", [architecture.md 8](../architecture.md) |
| ISM-1238 | Threat modelling supports the SDLC | Implemented | A written threat-model delta is a sign-off gate for every phase. | [threat-models/phase-0.md](../threat-models/phase-0.md) to [phase-3.md](../threat-models/phase-3.md) |
| ISM-2039 | Threat model reviewed through the SDLC to match the as-built system | Partial | Phases 0 to 3 are covered. Phase 4 added payments, entitlement checks and report signing but has no threat-model file yet. | Risk R11 |
| ISM-0401 | Secure by Design principles followed | Implemented | Fail-closed pipeline, least authority for the AI layer, narrow wallet interface, single signing path enforced in CI. | `agent/napg/agentshield/pipeline.py`, `agent/tests/test_codebase_invariants.py` |
| ISM-2042 | Secure by Default | Implemented | Actions default to dry-run; validation stages default to refusing; HTTPS-only RPC URLs enforced at config load. | `agent/napg/actions.py`, `agent/napg/config.py` |
| ISM-2040 | Secure programming practices for the language | Implemented | Strict pydantic models at every boundary, frozen result types, ruff lint and format gates, typed TypeScript. | `agent/pyproject.toml`, `ci.yml` |
| ISM-2023, ISM-2024 | Authoritative source for software established and used | Implemented | GitHub repository `apakuki/NAPG`; CI builds only from it. | `.github/workflows/ci.yml` |
| ISM-1422 | Unauthorised access to the authoritative source prevented | Partial | The repository is public by choice (read access intended). Write access is limited to the owner's account. Account MFA to confirm. | Risk R02 |
| ISM-1816 | Unauthorised modification of the authoritative source prevented | Partial | Only the owner can push. Since 14 Oct 2026 a ruleset on `main` requires a pull request and passing CI and blocks force-push and deletion. No second reviewer, so a compromised owner session could still merge. | [branch-protection.md](../runbooks/branch-protection.md), risk R02 |
| ISM-2030 | Commit-time secret scanning blocks secrets reaching the source | Partial | gitleaks pre-commit hook (opt-in) plus a full-history gitleaks scan in CI. CI runs after a push, so it detects rather than blocks a pushed secret. | `.pre-commit-config.yaml`, `ci.yml` security job |
| ISM-2028, ISM-0402 | Software tested with SAST, DAST and SCA | Partial | SCA: pip-audit and npm audit in CI. DAST: OWASP ZAP baseline against staging, zero high or critical findings (2 Jun 2026). No dedicated SAST tool (ruff and eslint are linters, not security analysers). | `ci.yml`, [phase-3.md scan results](../threat-models/phase-3.md) |
| ISM-2102 | Existing code periodically re-tested | Partial | SCA runs on every push and Dependabot weekly. DAST is a one-off, not scheduled. | `ci.yml`, `.github/dependabot.yml` |
| ISM-2154 | Dependencies pinned to approved versions | Implemented | `uv.lock` and `package-lock.json` committed; CI installs with `uv sync` and `npm ci`. GitHub Actions are pinned to major tags, not commit SHAs. | `agent/uv.lock`, `frontend/package-lock.json` |
| ISM-2029 | Third-party components restricted to trustworthy sources | Partial | Public PyPI and npm registries only, lockfile integrity hashes, Dependabot. No allow-listing of packages. | Lockfiles |
| ISM-2060, ISM-2061 | Code reviews and peer reviews on security-related components | Not implemented | Sole developer; no second human reviewer. Changes are AI-assisted and test-gated, which is not a substitute for peer review. | Risk R03 |
| ISM-1730 | Software bill of materials produced | Not implemented | Deferred in the Phase 0 threat model. | [phase-0.md accepted risks](../threat-models/phase-0.md), risk R08 |
| ISM-1755, ISM-1756 | Vulnerability disclosure policy and process | Implemented | Reporting address, 72-hour acknowledgement, 7-day triage, 90-day coordinated disclosure. | [SECURITY.md](../../SECURITY.md) |
| ISM-1616 | Vulnerability disclosure program | Partial | Policy published; no program (no bounty, no published triage record). | [SECURITY.md](../../SECURITY.md) |
| ISM-1240 | Validation and sanitisation of all input from the internet | Implemented | RPC, 0x, lending-market, Anthropic and Tenderly responses parsed through pydantic models before use; frontend checks addresses against a strict pattern. | `agent/napg/monitor/`, `frontend/src/lib/session.ts` |
| ISM-2058 | Serialised inputs validated before deserialisation | Implemented | All external JSON passes through typed models; unknown fields rejected on API card schemas. | `agent/napg/api.py`, `agent/napg/agentshield/stages/tenderly.py` |
| ISM-2057 | Input validation rules documented and tested with positive and negative tests | Partial | Validation is unit-tested, including rejection paths; rules are documented per module rather than in one place. | `agent/tests/` |
| ISM-2051 | Software generates sufficient event logs | Implemented | Every cycle writes scenario, breach, decision, validation and action rows. | `agent/napg/audit.py`, [architecture.md 2](../architecture.md) |
| ISM-2052 | Sensitive data in software event logs protected | Implemented | RPC URLs redacted at the probe boundary; tests assert API keys and the wallet secret never appear in audit rows. | `agent/napg/redact.py`, audit log tests |

## 3. Web application development

| Control | Requirement (short) | Status | How NAPG meets it | Evidence |
|---|---|---|---|---|
| ISM-1552 | All web content offered over HTTPS | Implemented | Public frontend served over HTTPS with HSTS. The agent has no public endpoint. | `frontend/next.config.ts`, [deploy-staging.md](../deploy-staging.md) |
| ISM-0971, ISM-1850 | OWASP ASVS used; OWASP Top 10 mitigated | Partial | CSP with per-request nonce, CSRF origin checks, rate limiting, output redaction, ZAP baseline clean. No formal ASVS verification against a chosen level. | `frontend/src/proxy.ts`, `frontend/src/lib/csrf.ts`, `frontend/src/lib/rate-limit.ts` |
| ISM-1241 | Output encoding on all web output | Implemented | React escapes rendered output by default; no third-party scripts; CSP blocks inline script without a nonce. | `frontend/e2e/csp.spec.ts` |
| ISM-2063 | Session cookies set HttpOnly, Secure and SameSite | Implemented | `napg_session` is HttpOnly, Secure in production, SameSite=Lax, no Domain attribute. | `frontend/src/lib/session.ts` |
| ISM-2064 | Session cookies contain only signed opaque bearer tokens | Partial | The cookie is HMAC-signed but not opaque: its body is readable base64 JSON holding the Farcaster ID, address and expiry. | `frontend/src/lib/session.ts`, risk R09 |
| ISM-2066 | Sessions centrally managed server side | Not implemented | Sessions are stateless signed cookies; a session cannot be revoked before expiry except by rotating the secret for everyone. | Risk R09 |

## 4. AI application development

| Control | Requirement (short) | Status | How NAPG meets it | Evidence |
|---|---|---|---|---|
| ISM-2113 | Human approval before sensitive or high-impact actions | **Not implemented (deviation)** | Autonomous by design. Compensating controls: dry-run default, four-stage fail-closed validation, independent judge model, per-transaction cap, 24-hour ceiling, fixed safe address, kill switch, testnet-only funds. | Risk R01 |
| ISM-2114 | Baselines of expected AI behaviour monitored for deviation | Not implemented | Decisions are logged but not trended or alerted on (for example, a sudden rise in migrate decisions). | Risk R12 |
| ISM-2133 | Each AI agent has a unique identity | Implemented | Dedicated wallet and API keys, separate from the owner's personal accounts. | [System security plan 6](system-security-plan.md) |
| ISM-2134, ISM-2135 | AI agent register maintained with identities, credentials, tools and data | Implemented | Register entry in this package. | [System security plan 6](system-security-plan.md) |
| ISM-2084 | AI system documentation (model and system cards) | Implemented | System card in this package plus the architecture document. | [System security plan 5](system-security-plan.md) |
| ISM-2085 | Exact confidence scores not exposed in APIs or UI | Implemented | Confidence is stored in the audit log only; the dashboard and public API do not show it. | `frontend/src/` (no confidence field rendered) |
| ISM-2090 | Rate limiting on inference queries | Partial | At most one reasoner call and one judge call per decision cycle; no explicit rate limiter or spend alarm on the Anthropic client. | `agent/napg/reasoning.py` |
| ISM-2156 | Agentic AI limited to minimum tools and permissions | Implemented | The reasoner has one tool (`submit_decision`) and cannot execute anything; the only action is a transfer to one pinned address. | `agent/napg/reasoning.py`, `agent/napg/actions.py` |
| ISM-2157 | Tool use subject to agent-specific, task-scoped authorisation | Implemented | Any transfer must pass AgentShield; the AI layer has no direct wallet access, enforced by a CI invariant test. | `agent/tests/test_codebase_invariants.py` |
| ISM-2158 | External content treated as untrusted, delimited, unable to override instructions | Partial | Probe data is schema-validated and passed as a separate JSON block, and the judge is independent. The reasoner's prompt does not explicitly label probe content as untrusted or forbid it from overriding instructions. | `agent/napg/reasoning.py`, [phase-2.md prompt injection](../threat-models/phase-2.md), risk R12 |
| ISM-2159 | All tool invocations, requests and outputs centrally logged | Partial | Every decision, validation and action is logged with full detail, but to a local SQLite file rather than a central logging facility. | `agent/napg/audit.py`, risk R07 |
| ISM-2103 | Organisational data not used for model training without consent | Implemented | API use only; no fine-tuning or training data supplied. | System card |
| ISM-2072, ISM-2086 | Model files non-executable; model source and integrity verified | N/A | No models are hosted or loaded; inference is a vendor API call. | - |

## 5. System access and credentials

| Control | Requirement (short) | Status | How NAPG meets it | Evidence |
|---|---|---|---|---|
| ISM-2142 | Application credentials centrally managed in a secrets solution | Partial | Staging uses Fly.io secrets. On the workstation, `.env`, `cdp_api_key.json` and `cdp_wallet_secret.txt` sit as plain files in the repository folder (git-ignored). The policy signing key is a file in the home directory. | [deploy-staging.md 4](../deploy-staging.md), `.gitignore`, risk R04 |
| ISM-1875 | Monthly scan for credentials stored in the clear | Partial | gitleaks covers the repository on every push; the workstation is not scanned. | `ci.yml` |
| ISM-1173 | MFA for privileged users | Implemented | MFA is on for the GitHub, Fly.io, Coinbase Developer Platform, Anthropic and Tenderly accounts (owner confirmed 14 Oct 2026). | Owner confirmation |

## 6. Security monitoring and event logging

| Control | Requirement (short) | Status | How NAPG meets it | Evidence |
|---|---|---|---|---|
| ISM-1405 | Centralised event logging facility | Not implemented | Audit log is a local SQLite file on the agent's volume; platform logs stay in Fly.io. | Risk R07 |
| ISM-1815 | Event logs protected from unauthorised modification and deletion | Partial | Row edits and deletes are blocked by triggers and detected by per-row HMAC. Deleting or replacing the whole database file is not prevented. | `agent/napg/audit.py`, risk R07 |
| ISM-1985 | Event logs protected from unauthorised access | Implemented | The agent has no public endpoint; the frontend exposes breach rows only, with HMACs dropped and output redacted. | `agent/napg/api.py` |
| ISM-0585, ISM-1959 | Each event has date, time, process and description; structured format | Implemented | Rows carry kind, UTC timestamp and a typed JSON payload. | `agent/napg/audit.py` |
| ISM-0988 | Accurate and consistent time source | Partial | Host UTC clock on Fly.io; no explicit time-source check. A slow clock makes block-age checks more suspicious, which is the safe direction. | [architecture.md 4.3](../architecture.md) |
| ISM-1988 | Logs kept searchable for at least 12 months | Not implemented | No retention period defined. | Risk R07 |
| ISM-1986 | Logs from critical servers analysed promptly | Partial | Breaches are acted on by the agent each cycle and shown in the breach feed; security events (for example failed sign-ins, validation failures) are not reviewed or alerted on. | `frontend/src/app/breaches/` |

## 7. Backups, supply chain and cryptography

| Control | Requirement (short) | Status | How NAPG meets it | Evidence |
|---|---|---|---|---|
| ISM-1511, ISM-1811 | Backups performed, retained securely and resiliently | Partial | Source is in GitHub. The audit database is on a Fly.io volume; snapshot schedule and retention to confirm. | [dependency-register.md](../dependency-register.md) |
| ISM-1515 | Backup restoration tested | Not implemented | No restore test recorded. | Risk R16 |
| ISM-1452 | Supply chain risk assessment for suppliers | Implemented | Dependency register with owner, criticality, detection, exit plan and recovery time for each external service. | [dependency-register.md](../dependency-register.md) |
| ISM-1139 | Only the latest TLS version used | Inherited | TLS terminated by Fly.io's edge for the frontend; outbound calls use the HTTP client's defaults. Not verified against ISM TLS settings. | - |
| ISM-1766 | SHA-2 with at least 224-bit output, preferably SHA-384 or SHA-512 | Implemented | HMAC-SHA256 for audit rows and session cookies. Meets the minimum; the preferred SHA-384 is not used. | `agent/napg/audit.py`, `frontend/src/lib/session.ts` |
| ISM-0475 / ISM-1991 | Approved digital signature algorithms (ECDSA, ML-DSA, RSA) | Partial | Configuration signing uses Ed25519, which is not on the ISM's approved list. Wallet signing is done by Coinbase's infrastructure. | `agent/napg/agentshield/policy.py`, risk R06 |
| ISM-2050 | Signatures validated against a certificate trust chain and revocation | N/A | Config signatures use a pinned public key committed to the repository, not certificates. | `agent/config/policy_public_key.pem` |

## Controls recorded as not applicable

Windows, Microsoft Office and Active Directory hardening; email gateways; physical security; personnel security and awareness training (no staff); communications infrastructure and multifunction devices; evaluated product procurement; cross-domain solutions and gateways. NAPG runs on a managed platform with no organisation-owned network equipment.
