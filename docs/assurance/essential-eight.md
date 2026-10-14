# Essential Eight self-assessment: NAPG

Version 0.1, 14 October 2026. Assessed against the Essential Eight Maturity Level One (ML1) baseline in the ISM September 2026 release.

## Scope and caveat

The Essential Eight is written for internet-connected Microsoft Windows networks. NAPG has no Windows estate: it is two containers on Fly.io, a GitHub repository, a set of cloud service accounts, and one macOS workstation used to build and administer it. This assessment therefore applies each strategy to that environment:

- **Workstation:** the owner's macOS laptop (development, signing keys, administration).
- **Online services:** GitHub, Fly.io, Coinbase Developer Platform, Anthropic, Tenderly, 0x.
- **Servers:** the two Fly.io applications and their base images.

Where a requirement depends on settings that cannot be seen from the repository, it is marked **To confirm**. Overall maturity for each strategy is the lowest level all its ML1 requirements meet.

## Summary

| Strategy | Current maturity | Main gap to ML1 |
|---|---|---|
| Patch applications | ML0 | Known advisories accepted beyond the ML1 timeframes; workstation browser not updated automatically |
| Patch operating systems | ML0 | macOS not updated automatically; Fly.io image rebuild cadence to confirm |
| Multi-factor authentication | ML1 | Met. Moving to phishing-resistant passkeys would support higher levels |
| Restrict administrative privileges | ML0 | One account used for both daily work and administration |
| Application control | ML0 | No application control on the workstation |
| Restrict Microsoft Office macros | N/A | No Microsoft Office in scope |
| User application hardening | To confirm | Browser settings on the workstation |
| Regular backups | ML0 | Restore never tested; snapshot schedule to confirm |

The honest summary: NAPG's application-level security is strong, but the Essential Eight measures the environment around it, and that environment is a single person's laptop and accounts. Most of the work to reach ML1 is account and workstation configuration, not code.

## Strategy by strategy

### Patch applications

| ML1 requirement | Status | Notes |
|---|---|---|
| ISM-1807, ISM-1808: automated asset discovery and an up-to-date vulnerability scanner | Partial | Dependabot, pip-audit and npm audit cover application dependencies; there is no scanner for the workstation. |
| ISM-1698: scan online services daily | Partial | Dependency scans run on every push, not on a daily schedule. |
| ISM-1876, ISM-1690: patch online services within 48 hours (critical or exploited) or two weeks | Not met | Eight advisories are allow-listed because an upstream SDK pins vulnerable versions (risk R17). Accepting known vulnerabilities beyond these timeframes does not meet ML1, even with a documented reason. |
| ISM-1691, ISM-1704: patch browsers and other workstation applications within two weeks; remove unsupported ones | Not met | Browser updates are not automatic and manual updates are not tracked (owner confirmed 14 Oct 2026). |

**To reach ML1:** add a daily scheduled run of the dependency audit; track each allow-listed advisory with a review date; turn on automatic browser and application updates.

### Patch operating systems

| ML1 requirement | Status | Notes |
|---|---|---|
| ISM-1877, ISM-1694: patch internet-facing server operating systems within 48 hours (critical or exploited) or two weeks | To confirm | The Fly.io apps run on container base images defined in the Dockerfiles; they are patched only when the image is rebuilt and redeployed. |
| ISM-1695: patch workstation operating systems within one month | Not met | macOS updates are not automatic and manual updates are not tracked (owner confirmed 14 Oct 2026). |
| ISM-1501: replace unsupported operating systems | To confirm | macOS version support status. |

**To reach ML1:** rebuild and redeploy both images at least fortnightly (or on a base-image security release); turn on macOS automatic updates, including security responses and system files.

### Multi-factor authentication

| ML1 requirement | Status | Notes |
|---|---|---|
| ISM-1504, ISM-1679, ISM-1680: MFA for online services holding the organisation's data | Met | Owner confirmed MFA on GitHub, Fly.io, Coinbase Developer Platform, Anthropic and Tenderly (14 Oct 2026). The 0x account holds only an API key and should be checked too. |
| ISM-1401: MFA is something you have plus something you know, or a device unlocked by something you know or are | Met | Record which method each account uses; prefer passkeys or authenticator apps over SMS. |
| ISM-1681, ISM-1892: MFA for online customer services holding sensitive customer data | N/A | The dashboard holds no sensitive customer data. Users sign in with Farcaster (a wallet signature) and a passkey-backed wallet, which is strong authentication in any case. |

**Status:** ML1 met for MFA. Next step is to switch any SMS-based accounts to passkeys.

### Restrict administrative privileges

| ML1 requirement | Status | Notes |
|---|---|---|
| ISM-1507: privileged access validated when first requested | N/A | Single owner; there is no one else to request access. |
| ISM-0445: dedicated privileged account used only for privileged duties | Not met | Owner confirmed there is no separate macOS administrator account (14 Oct 2026); the same personal accounts are also used to administer GitHub, Fly.io and the wallet. |
| ISM-1175, ISM-1883: privileged accounts kept off general web and email | Not met | Follows from the above. |

**To reach ML1:** use a separate standard macOS user for daily browsing and email, and a separate administrator account; where a service supports it, use a separate administrative login or role for production changes.

### Application control

| ML1 requirement | Status | Notes |
|---|---|---|
| ISM-0843, ISM-1870, ISM-1657: application control on workstations, including user and temporary folders | Not met | macOS Gatekeeper checks code signing, but that is not application control as the ISM defines it. |

**To reach ML1:** use an allow-listing tool on the workstation (for example Santa) in monitor mode first, then enforce. This is the hardest strategy for a development machine, which runs many unsigned build tools.

### Restrict Microsoft Office macros

Not applicable. No Microsoft Office applications are used in the system boundary.

### User application hardening

| ML1 requirement | Status | Notes |
|---|---|---|
| ISM-1486, ISM-1485: browsers block Java and web advertisements from the internet | To confirm | Workstation browser settings. |
| ISM-1585: browser security settings cannot be changed by users | N/A for one person | Applies to managed fleets. |
| ISM-1654: Internet Explorer 11 disabled | N/A | macOS. |

### Regular backups

| ML1 requirement | Status | Notes |
|---|---|---|
| ISM-1511, ISM-1810, ISM-1811: backups performed, synchronised and retained securely | Partial | Source is in GitHub; the audit database is on a Fly.io volume with snapshots (schedule and retention to confirm). The signing keys on the workstation have no documented backup. |
| ISM-1812, ISM-1814: unprivileged accounts cannot read, change or delete backups | To confirm | Depends on Fly.io account access. |
| ISM-1515: restoration tested | Not met | Never tested (risk R16). |

**To reach ML1:** confirm the snapshot schedule; back up the policy signing key and audit HMAC key to an encrypted, offline location; restore a snapshot and run `napg audit verify` once, then once a year.

## Path to Maturity Level One

In order of effort:

1. Done: MFA on every service account (MFA).
2. Turn on automatic macOS and browser updates (patch operating systems, patch applications).
3. Back up the signing and HMAC keys offline, and test a restore of the audit database (backups).
4. Schedule a daily dependency audit and a fortnightly image rebuild (patching).
5. Split daily and administrator accounts on the workstation (restrict administrative privileges).
6. Pilot application control in monitor mode (application control).
