# Risk register: NAPG

Version 0.1, 14 October 2026. Owner: Samuel Nayacakalou.

This register holds the residual risks left after the controls in the [control mapping](control-mapping.md). Engineering-level threats and their mitigations stay in the [threat models](../threat-models/); this register is the system-level view a system owner signs. Risks the threat models already accepted are carried here so they are visible in one place.

## Rating method

Likelihood × consequence, each scored 1 to 5, rated as the system stands today (testnet funds, staging only).

| Score | Likelihood | Consequence |
|---|---|---|
| 1 | Rare | Minimal: no fund loss, no data exposure |
| 2 | Unlikely | Minor: testnet loss or brief outage |
| 3 | Possible | Moderate: integrity of records or controls weakened |
| 4 | Likely | Major: loss of real funds or a control bypassed in production |
| 5 | Almost certain | Severe: large loss of real funds or loss of trust in the system |

Rating bands: **Low** 1 to 4 · **Medium** 5 to 9 · **High** 10 to 16 · **Extreme** 20 to 25.

"Mainnet gate" means the risk must be re-rated and either treated or formally re-accepted before real funds are used.

## Register

| ID | Risk | L | C | Rating | Existing controls | Treatment | Status | Mainnet gate |
|---|---|---|---|---|---|---|---|---|
| R01 | The agent moves funds without a human approving the action, contrary to ISM-2113. A wrong but plausible decision could move funds unnecessarily. | 3 | 2 | Medium | Dry-run default; four-stage fail-closed validation; independent judge model; per-transaction cap; 24-hour ceiling; single pinned safe address; kill switch | **Accept for testnet.** Autonomy is the product's purpose, and a transfer to the owner's own safe address is recoverable. Before mainnet, decide between a human-approval step above a value threshold or a written risk acceptance. | Accepted (testnet) | Yes |
| R02 | Branch protection is off on a public repository. A compromised GitHub session could push a change that swaps the policy public key or removes a guard, with nothing blocking it. The Phase 0 trigger to re-enable protection ("the repo goes public") has already been met. | 3 | 4 | High | Single owner with write access; CI runs on every push; signed config | **Treated 14 Oct 2026.** Ruleset `protect-main` enabled: pull request and all three CI checks required, force-push and deletion blocked, no bypass. Required reviews stay at 0 while there is one maintainer. Residual: a compromised session could still merge a pull request that passes CI. | Treated | Yes |
| R03 | No independent review of code or security changes. Errors and weak designs are only caught by the author and the tests. | 3 | 3 | Medium | Threat model per phase; 80% coverage floor; CI security scans; external design reviews (dependency register) | **Treat before mainnet.** External security audit already planned (PLAN.md W10). Add a second reviewer if a collaborator joins. | Open | Yes |
| R04 | Long-lived secrets (CDP API key, wallet secret, API keys) are plain files on the operator workstation, inside the repository folder. Theft of the laptop or malware could expose them. | 2 | 3 | Medium | Files git-ignored; gitleaks pre-commit and CI; testnet-only wallet; [key-compromise runbook](../runbooks/key-compromise.md) | **Treat.** Move workstation secrets into the macOS Keychain or a password-manager CLI and load them at run time; move the files out of the repository folder. | Open | Yes |
| R05 | The policy signing key and audit HMAC key have no hardware protection. Whoever holds them can re-sign a hostile policy or re-sign tampered audit rows. | 2 | 4 | Medium | Keys outside the repository (chmod 600); public key change visible in review; rotation steps in runbook | **Accept for testnet**, as recorded in the Phase 2 threat model. Move to a hardware-backed key store at mainnet. | Accepted (testnet) | Yes |
| R06 | Configuration is signed with Ed25519, which is not among the ISM's approved signature algorithms (ECDSA, ML-DSA, RSA). A government deployment would not accept it as is. | 1 | 3 | Low | Signature is checked on every load; pinned public key | **Accept** for a non-government system. If the system is ever offered to government, move to ECDSA P-384 (ISM-0475) or ML-DSA-87 (ISM-1991). | Accepted | No |
| R07 | The audit log is a single SQLite file on one volume. It is not sent to a central log store, no retention period is set, and deleting or replacing the whole file is not prevented, only row edits. | 2 | 3 | Medium | Append-only triggers; per-row HMAC; `napg audit verify` | **Treat before mainnet.** Ship audit rows to an external append-only store as they are written; set 12-month retention (ISM-1988). | Open | Yes |
| R08 | No software bill of materials, so consumers and the owner cannot quickly check exposure to a newly announced vulnerable component. | 2 | 2 | Low | Lockfiles; pip-audit and npm audit on every push; Dependabot | **Treat.** Generate a CycloneDX SBOM in CI for both agent and frontend and attach it to releases. | Open | No |
| R09 | Sessions are stateless signed cookies. A stolen cookie stays valid until expiry; the only way to revoke it is to rotate the secret for every user. The cookie body is readable, not opaque. | 2 | 2 | Low | HttpOnly, Secure, SameSite=Lax; HMAC verified in constant time; no fund authority in the frontend | **Accept for testnet.** Move to server-side session records when the shared store lands in Phase 5. | Accepted (testnet) | Yes |
| R10 | No consolidated incident response plan or incident register, and kill-switch authority is still an open decision. In a real incident, who decides and who is told is undefined. | 3 | 3 | Medium | Five scenario runbooks; kill switch; audit log | **Treat before mainnet.** Write one incident response plan covering ISM-0043 and an incident register (ISM-0125); record the kill-switch authority decision. | Open | Yes |
| R11 | Phase 4 added payments, entitlement checks and report signing without a written threat model, so their threats and accepted risks are not recorded. | 3 | 3 | Medium | Unit tests on the Phase 4 modules | **Treat now.** Write `docs/threat-models/phase-4.md` before further Phase 5 work. | Open | Yes |
| R12 | Manipulated protocol data could steer the reasoner (prompt injection), and there is no monitoring for unusual decision patterns. | 2 | 2 | Low | Schema validation; independent judge; deterministic policy stage; caps | **Treat.** Label probe data as untrusted in the reasoner prompt (ISM-2158) and alert on decision-rate anomalies (ISM-2114). | Open | Yes |
| R13 | Signing, chain and settlement asset all depend on the Coinbase and Circle ecosystem, so one incident there affects all three at once. | 2 | 4 | Medium | Fail-safe on outage; treasury limits; 24-hour outage assumption | **Accept** as an inherent product choice; disclose it in any risk statement, as the [dependency register](../dependency-register.md) requires. | Accepted | Yes |
| R14 | The simulation stage does not yet check exact balance changes, so a misleading simulation result would not be caught by that stage. | 2 | 2 | Low | Value cap; pinned safe address; gas-window check | **Accept for testnet** (Phase 2 threat model); implement full state-diff checks in Phase 5. | Accepted (testnet) | Yes |
| R15 | The kill switch is checked at the start of validation, so a transfer already past that check can still complete if the switch is engaged one to three seconds later. | 2 | 2 | Low | Synchronous pipeline; next cycle is blocked | **Accept for testnet**; move the check to the wallet edge at mainnet. | Accepted (testnet) | Yes |
| R16 | Backups of the audit database have never been restored in a test, so recovery after volume loss is unproven. | 2 | 3 | Medium | Fly.io daily volume snapshots, 5-day retention; HMAC verification after restore | **Treat.** Restore a snapshot to a scratch volume, run `napg audit verify`, and record the result. | Open | Yes |
| R17 | Eight known dependency advisories are allow-listed in CI because an upstream SDK pins vulnerable versions, two with no fix released. | 3 | 2 | Medium | Each advisory documented in `ci.yml` with its reason; re-checked on every SDK release | **Accept** with review at every upstream SDK bump; record the review date. | Accepted | Yes |
| R18 | Rate limiting trusts the `X-Forwarded-For` header, so an attacker could spoof addresses to dodge per-IP limits in production. | 3 | 1 | Low | Rate limit per route; no fund authority behind those routes | **Accept for testnet**; pin a trusted-proxy header in Phase 5 (Phase 3 threat model). | Accepted (testnet) | Yes |
| R19 | The operator workstation uses one administrator account for daily work. This is the machine that holds the signing keys and secrets (R04, R05), so malware running in that account has admin rights and access to everything. Until 14 Oct 2026 the workstation was also more than a year behind on macOS patches (15.5, with 15.8.1 available). | 2 | 3 | Medium | MFA on every service account; testnet-only funds; keys outside the repository; macOS 15.8.1 with automatic installation of updates and security responses, and Chrome self-updating (both from 14 Oct 2026) | **Patching treated 14 Oct 2026** (rated High, 4 × 3, before). **Treat:** use a standard account for daily work and a separate administrator account. | Partly treated | Yes |

## Priorities

1. **Now:** R11 (Phase 4 threat model), R04 (move workstation secrets), R19 (separate administrator account). R02 and the patching part of R19 were treated on 14 October 2026.
2. **Before mainnet:** R01 decision, R03 external audit, R07 central logging, R10 incident response plan, R16 restore test.
3. **Carried:** the accepted testnet risks are re-rated at the mainnet gate, where real funds raise the consequence scores.

## Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| System owner | Samuel Nayacakalou | Accept the "Accepted (testnet)" items; treat the "Open" items as prioritised above | Pending |
