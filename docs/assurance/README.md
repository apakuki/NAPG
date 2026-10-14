# NAPG security assurance package

Status: **draft v0.1, 14 October 2026.** Author: Samuel Nayacakalou (system owner and sole developer).

This folder applies the Australian Government Information Security Manual (ISM) and the Essential Eight to NAPG, the way a system would be documented ahead of an IRAP assessment. It is a self-assessment written by the system's own developer, not an independent assessment, and NAPG is not a government system and holds no official or classified information. The point is to show the work of turning ISM requirements into implemented, evidenced controls, and to be honest about where NAPG falls short.

## What is in the package

| Document | What it answers | ISM reference |
|---|---|---|
| [System security plan](system-security-plan.md) | What the system is, where its boundary sits, how it is managed, and the AI agent register entry | ISM-0041, ISM-2084, ISM-2134 |
| [Control mapping](control-mapping.md) | For each applicable ISM control: status, how NAPG meets it, and the evidence in this repository | Annex to ISM-0041 |
| [Risk register](risk-register.md) | Residual risks, their rating, the treatment chosen, and what is accepted | ISM-1526 |
| [Essential Eight self-assessment](essential-eight.md) | Maturity against each of the eight mitigation strategies, and the plan to reach Maturity Level One | Essential Eight ML1 baseline |

## Basis of assessment

- **ISM release:** September 2026, taken from ASD's OSCAL catalogue (`ism-oscal` release `v2026.09.4`). Control identifiers are quoted exactly as published in that release.
- **Baseline used:** ISM non-classified baseline, plus the Essential Eight Maturity Level One baseline. Controls that only apply to Windows, Microsoft Office, email gateways, physical facilities or organisations with staff are recorded as not applicable rather than silently dropped.
- **Point in time:** the repository as of branch `phase5/w8-discovery-log` on 14 October 2026, and the Fly.io staging deployment described in [deploy-staging.md](../deploy-staging.md). There is no production deployment yet.

## How this package relates to the rest of the docs

The package does not repeat the engineering detail. It points to the documents that already hold the evidence:

- [Architecture](../architecture.md): how the system is built.
- [Threat models](../threat-models/): per-phase threats, mitigations and accepted risks (phases 0 to 3).
- [Dependency register](../dependency-register.md): third-party dependencies, criticality and exit plans.
- [Runbooks](../runbooks/): key compromise, kill switch, infrastructure outage, emergency migration and false-positive breach procedures.
- [SECURITY.md](../../SECURITY.md): vulnerability disclosure policy.

## Headline findings

1. **Strong on secure development.** Per-phase threat modelling, fail-closed validation before any signature, signed configuration, a tamper-evident audit log, secret scanning, dependency auditing, a DAST scan against staging, and pinned dependencies all map cleanly to ISM software development controls.
2. **One deliberate deviation.** ISM-2113 expects human approval before an AI application takes a high-impact action. NAPG is designed to act autonomously within hard limits. That is recorded as a deviation with compensating controls and an explicit risk acceptance (risk R01).
3. **Governance gaps a solo project cannot close alone.** No independent code review, no consolidated incident response plan, no incident register and no SBOM. Branch protection had been left off after the repository went public; it was re-enabled on 14 October 2026 as a result of this assessment.
4. **Cryptography would need changing for government use.** Configuration signing uses Ed25519, which is not among the ISM's approved signature algorithms (ECDSA, ML-DSA, RSA).

## Open items for the system owner to confirm

Some controls depend on account settings that cannot be read from the repository. They are marked "To confirm" in the control mapping and the Essential Eight assessment:

- Fly.io volume snapshot schedule and retention for the audit database.
- Browser settings for Java and web advertisements on the operator workstation.
- Fly.io base image rebuild cadence.

Confirmed by the owner on 14 October 2026: MFA is on for every service account; there is no separate macOS administrator account; macOS and browser updates are not automatic.
