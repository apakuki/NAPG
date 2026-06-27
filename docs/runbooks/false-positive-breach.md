# Runbook: false-positive breach

Status: **procedure drafted.** Written 2026-06-28 after an external review noted
that false positives are constant in monitoring systems and "NAPG wants to
migrate but there is actually no risk" needs a defined response.

A false positive is when a Service Level Breach fires (and may drive a migration)
but the underlying state is fine — the signal was an artefact, not a threat.
Migrating on a false positive is costly: gas, disruption, and for Guardian
subscribers, alarm. But *suppressing* a real breach is far worse. The bias is
deliberately toward acting; this runbook is how to handle the false-positive tail
without weakening that bias.

## Common causes

| Symptom | Likely artefact, not threat |
|---|---|
| `reorg_detected` spike | RPC node briefly served an inconsistent view / failover between nodes |
| `rpc_latency_ms_max` / `block_age_seconds_max` | One RPC provider degraded; the chain is fine (the failover heartbeat should mask this) |
| `peg_deviation_bps_max` | Stale or thin 0x quote, single-source pricing artefact (review #13: multi-source pricing not yet built) |
| `market_utilization` / `staleness` | Indexer lag or a single bad poll, not a real market move |

The thread: **single-source signals produce false positives.** The durable fix is
corroboration (multi-RPC, multi-oracle, TWAP) — review #13, tracked for the
monitoring hardening backlog. Until then, the human check below is the control.

## What protects against acting on one today

- The **reasoner** sees the full probe bundle, not just one breach, and weighs
  corroboration before proposing `migrate_to_safe`.
- **Stage 1 Intent Judge** independently checks the proposed action against the
  stated goal (and, post-hardening, runs on a different Claude model — decision 6
  — so it does not share the planner's exact failure mode).
- A single transient breach that clears on the next cycle does not by itself
  force a migration; sustained / corroborated signals do.

## Operator procedure

1. **Cross-check the trigger against an independent source.** RPC issue → query a
   second RPC / a block explorer. Peg → check a second venue (Coinbase spot,
   another DEX). Market → check the protocol UI directly. If independent sources
   disagree with the breach, it is likely a false positive.
2. **Check whether it already self-cleared.** Look at the breach feed: did the
   next cycle still breach, or recover? A one-cycle blip that recovered is almost
   always an artefact.
3. **If confirmed false positive and a migration is pending/proposed:** engage
   the [kill switch](kill-switch.md) to stop the migration being initiated, then
   record *why* it was a false positive in the incident log. Do not silently
   dismiss — the record is what tunes thresholds later.
4. **If genuinely uncertain:** bias toward the migration. A safe-state native
   transfer is reversible-at-leisure (see
   [emergency-migration.md](emergency-migration.md) rollback); an un-rescued
   exploit is not. Uncertainty is not a reason to suppress.

## Tuning, not suppressing

After a confirmed false positive, the follow-up is a **threshold or corroboration
change in `config/breaches.toml`**, reviewed and committed — never an ad-hoc mute.
Recurring false positives on one signal are the strongest argument for landing
its multi-source corroboration (review #13). Every false positive should leave
either a config change or a backlog item; none should leave just a dismissal.

## Anti-goal

Do not build an auto-suppression that silences breaches without a human deciding
and a record landing. The append-only audit log must always show what fired, what
was decided, and why — a silently-muted real breach is the failure mode this
whole system exists to prevent.
