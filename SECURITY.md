# Security Policy

## Scope

NetAssure Protocol Guardian (NAPG) is greenfield software. The codebase under active development on `main` is the only supported branch. There is no production deployment yet — Phase 5 of [PLAN.md](PLAN.md) covers mainnet cutover, and this policy will be revised then.

## Reporting a vulnerability

Email: apakuki@gmail.com

Please do not open a public GitHub issue for security reports. Include:

- A description of the issue and its impact.
- Steps to reproduce, or a proof of concept.
- The commit hash or version where you found it.
- Whether you would like credit in the resolution notes.

Expect an acknowledgement within 72 hours and a triage assessment within 7 days. Issues affecting wallet signing, AgentShield, or the audit log take priority.

## Coordinated disclosure

We ask that you do not publish details until a fix has been released or 90 days have passed, whichever comes first. We will keep you informed of progress.

## Out of scope

- Issues only reproducible against forks or unsupported branches.
- Social-engineering or physical attacks against contributors.
- Findings against third-party dependencies — please report those upstream, then ping us once the upstream advisory exists so we can pin or patch.

## Hardening contributions

Pull requests that add tests, hooks, or CI scans which catch a class of bug are welcome. Open one against `main` with a short rationale.
