# NAPG manual test procedures

Runbooks for hands-on verification of each phase. Read the phase's manual-test doc before sign-off; tick the boxes as you go. These are written in the same symptom-action style as the troubleshooting blocks in [PLAN.md](../../PLAN.md) — if a step fails, the troubleshooting section for that phase is the next stop.

## Index

| Phase | File | Status |
|-------|------|--------|
| Phase 0 | [phase-0.md](phase-0.md) | Ready — scaffolding is committed |
| Phase 1 | [phase-1.md](phase-1.md) | Skeleton — populated as monitors land |
| Phase 2 | [phase-2.md](phase-2.md) | Skeleton — populated when AgentShield lands |
| Phase 3 | [phase-3.md](phase-3.md) | Skeleton — populated when frontend lands |
| Phase 4 | [phase-4.md](phase-4.md) | Skeleton — populated when x402 / Builder Code lands |
| Phase 5 | [phase-5.md](phase-5.md) | Skeleton — populated for mainnet cutover |

## How to use these documents

1. Open the phase's doc before sign-off.
2. Run each procedure in order on a clean working tree.
3. Tick the checkbox if the actual result matches the expected result.
4. If anything fails, jump to the phase's Troubleshooting section in [PLAN.md](../../PLAN.md) before retrying.
5. Record any deviations or environment notes inline so the next runner has them.

## Conventions

- All commands assume the repo root as cwd unless stated.
- "Expected" describes the success state. "Failure mode" lists the most common reasons it goes wrong.
- Where a procedure depends on a `.env` value, the variable name is named explicitly.
- Network calls are flagged so air-gapped runs can skip them and re-do later.
