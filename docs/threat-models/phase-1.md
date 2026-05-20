# Phase 1 threat model — Prototype and Logic Core

Scope: the agent core that lands in Phase 1 — the RPC heartbeat, the 0x liquidity probe, the Morpho Blue lending poller, the breach-evaluator, the Anthropic reasoning layer, the CDP-backed testnet wallet, and the SQLite audit log. The frontend dashboard is out of scope (it lands in [Phase 3](phase-3.md) once written).

This document is the written threat-model delta required by [PLAN.md](../../PLAN.md#cross-cutting-security-baseline) for Phase 1 sign-off. It builds on [phase-0.md](phase-0.md) by adding the new attack surface introduced by live network I/O, an LLM, and a signing path.

## New surface introduced this phase

- Outbound HTTPS to managed RPC providers (Alchemy, etc.) — both Sepolia and mainnet, mainnet read-only for Morpho.
- Outbound HTTPS to the 0x API for pool quotes.
- Outbound HTTPS to the Anthropic API for reasoning.
- Outbound CDP API for wallet operations; the wallet itself is MPC, keys live in CDP TEE.
- A local SQLite audit log at `NAPG_AUDIT_DB` (default `./audit.db`) with HMAC-chained rows.
- Secrets in `.env`: Anthropic key, CDP key + private key + wallet secret, 0x key, audit HMAC key. Phase 0 already covers "don't commit these"; Phase 1 covers "what happens if one of them, or an upstream, is hostile."

## Trust model

- The agent's own dev box is trusted (same as Phase 0).
- `.env` and the CDP wallet secret file are trusted but precious.
- The audit log is trusted as a *record*; tamper-evidence (append-only triggers + per-row HMAC) is what makes it durable.
- Every external endpoint — RPC, 0x, Anthropic, CDP — is treated as **hostile by default**. Responses are parsed through Pydantic before any code acts on them, and side-effects (especially anything that could trigger a signature) are gated behind the breach-evaluator and (from Phase 2) AgentShield.
- The reasoning layer's output is treated as advisory: a malformed or hostile-looking response causes the cycle to abort, not to default to action.

## Threats and failure paths

### A lying RPC

**What that looks like:** an RPC that returns plausible-looking blocks that don't reflect chain state (stale head, replayed history, fabricated parent hash, malformed numeric fields, or a totally wrong `chain_id`).

**Mitigations:**
- `BlockSnapshot` (`napg.monitor.rpc`) validates `number`, `hash`, `parent_hash`, `timestamp` via Pydantic. Non-hex hashes, negative numbers, wrong types — all rejected at the boundary before anything downstream sees them.
- `RpcHeartbeat._detect_reorg` chains each block to the previous one *we recorded*, not to a value the same RPC supplied later. A provider can't rewrite history we already stored locally.
- `block_age_seconds_max` and `rpc_latency_ms_max` thresholds in `napg.policy.breaches` catch a stale-head attack — a provider that "freezes" the chain head trips both signals.
- `FailoverRpcHeartbeat` (`napg.monitor.resilience`) carries a circuit-breaker per provider: 3 consecutive failures trip a 30 s cooldown and the call falls through to a fallback RPC. This is also the hook for cross-checking two providers once we want active verification (left for a follow-up).
- The same gate pattern wraps the Morpho mainnet RPC reads via the `gated_call` helper — single-provider only (no failover yet), but the limiter and breaker still apply, so a misbehaving mainnet RPC degrades the Morpho card without spamming the upstream or tipping the rest of the cycle into retry loops.
- HTTPS-only at config-load (`Settings._require_https`) — no plaintext endpoint can ever be configured.
- URLs are redacted before they reach logs or the audit DB (`napg.redact.redact_url`); a hostile provider can't smuggle data into the log just by being in the URL.

**Residual risk:** a single provider can lie about the *current* head and we'll act on it for one cycle until the reorg or staleness signal fires on the next tick. Cross-provider attestation (compare head against the fallback before deciding) is the next mitigation; deferred until Phase 2 lands the wider AgentShield pipeline that already has a place to slot a cross-check in.

### A hostile 0x response

**What that looks like:** the 0x API returns a `quote` that prices USDC/USDT off-peg by enough basis points to look like a depeg, or returns a route field engineered to look like an Aerodrome pool when it isn't, or replies with fields the Pydantic model doesn't expect.

**Mitigations:**
- `LiquidityProbe` and the underlying response model (`napg.monitor.aerodrome`) parse the 0x payload through Pydantic — junk types and missing fields fail closed.
- The 0x call is gated by the same `RateLimiter` + `CircuitBreaker` pair as the RPC heartbeat (via `gated_call`): a 429 or 5xx storm from 0x trips the breaker after 3 consecutive failures and cools down for 30 s rather than hammering the upstream. The Aerodrome card degrades to an error envelope while the rest of `/api/status` keeps serving.
- A `peg_deviation_bps` over the configured threshold is *only one input* to the reasoner; the reasoner is told the source ("0x quote") and is instructed (in `SYSTEM_PROMPT`) not to migrate on a single-signal depeg without a corroborating heartbeat or Morpho signal. This survives a single-source manipulation.
- The `sources` field is treated as advisory only — it never gates any onchain action. A crafted "Aerodrome_V3" label cannot escalate the cycle.

**Residual risk:** if 0x is fully compromised, both quote and route are hostile; we depend on reasoning-layer corroboration. From Phase 2 onward, Tenderly simulation pre-flight gives a second independent view of the tx outcome.

### Malformed or hostile Anthropic output

**What that looks like:** the API returns a payload missing the `submit_decision` tool_use block, returns a block whose `input.intent` isn't in the allowed enum, returns mismatched JSON, or returns a confidence value outside [0, 1].

**Mitigations:**
- `Reasoner.decide` requires a `submit_decision` tool_use block (`_extract_tool_input`) — anything else raises `RuntimeError` and the cycle aborts. **No action means no signature**, which is the safe default.
- The `Decision` Pydantic model constrains `intent` to `{"hold", "migrate_to_safe", "pause_for_investigation"}` and `confidence` to `[0, 1]`. An out-of-band value fails Pydantic validation; the cycle aborts before reaching the dispatch step.
- The orchestrator dispatches only when `decision.intent == "migrate_to_safe"`; `hold` and `pause_for_investigation` never call the wallet. A Pydantic validation failure on the decision will short-circuit before either branch.
- The Anthropic API key is loaded via `Settings`, logged as `***`, never written to the audit DB. `test_audit_row_never_contains_the_api_key` asserts this in CI.

**Residual risk:** the model could pick `migrate_to_safe` when humans would say "hold." This is what the AgentShield Intent-Judge (Phase 2) is for — a separate LLM-side check that the proposed action matches the stated goal — and what the per-tx caps, denylist, and Tenderly simulation gates that follow it are for. Phase 1 ships with a tight Sepolia wallet balance as the practical cap.

### Audit log tamper

**What that looks like:** an attacker with write access to the DB file rewrites a `decision` row to hide why a tx was issued, or rewrites a `breach` row to make a false positive look real.

**Mitigations:**
- Schema-level append-only triggers (`audit_log_no_update`, `audit_log_no_delete`) reject `UPDATE`/`DELETE` at the SQLite layer. Manually demonstrated in [manual test 1.7](../manual-tests/phase-1.md#17--audit-log-integrity).
- Per-row HMAC-SHA256 with a separate key (`NAPG_AUDIT_HMAC_KEY`) gives a second line of defence — even if an attacker drops the triggers and rewrites a row, `napg audit verify` recomputes every HMAC and reports the tampered rows.
- The HMAC key never lands in the DB; it's loaded from env only. `test_audit_row_never_contains_the_api_key` and the audit-log tests assert this end-to-end.

**Residual risk:** an attacker with both DB write *and* the HMAC key can rewrite history undetectably. Phase 5 mainnet cutover lands daily encrypted off-box backups; the gap between "tamper happens" and "tamper is detected" is bounded by the backup cadence.

### Wallet abuse

**What that looks like:** an attacker who can run the agent process triggers `napg migrate --execute` with a malicious destination, or convinces the reasoner to do so via a prompt-injection in protocol state.

**Mitigations:**
- MPC-only wallet (`napg.wallet.build_agent_wallet`). Keys never enter the Python process; signing happens inside the CDP TEE. Compromise of the dev box doesn't directly expose keys.
- Sepolia-only for Phase 1; balance capped to dust. The worst case is loss of testnet ETH.
- Migration destination is read from `NAPG_SAFE_CONTRACT_ADDRESS` in `.env`, not from the reasoner's output. Even if the reasoner is fully prompt-injected, the destination it can pick is constrained to "the configured safe address."
- Dry-run by default; `--execute` is opt-in per invocation. The orchestrator's `dry_run` parameter defaults to `True`.
- Every action writes an `action` row to the audit log *before* the receipt poll completes, so an aborted receipt poll still leaves a recoverable record.

**Residual risk:** an attacker with the dev box can still flip `NAPG_SAFE_CONTRACT_ADDRESS` to their own wallet and invoke `--execute`. Phase 2's denylist + signed policy config is what closes this — the safe address becomes part of a signed config the loader will reject if tampered with. Mainnet (Phase 5) tightens further with per-tx/daily/weekly caps in AgentShield.

### Prompt-cache poisoning

**What that looks like:** an attacker manipulates the user-message content so that subsequent cached calls reuse a poisoned prefix.

**Mitigations:**
- The cached block is the `SYSTEM_PROMPT` only — a static string in `napg.reasoning`. User-message content (the protocol state) is *not* cached; each call carries fresh JSON.
- The cached system prompt has no user-influenced content; it can only be poisoned by a code change, which is gated by code review (Phase 0 baseline).

**Residual risk:** none significant at this phase. Once Phase 2 lands AgentShield, that policy is also code-reviewed and follows the same signed-config principle.

### Secrets at rest

**What that looks like:** an attacker reads `.env` or `cdp_wallet_secret.txt` off the dev box.

**Mitigations:**
- Both are gitignored (Phase 0 baseline; verified by manual test 0.6).
- The CDP wallet secret file path is in `.gitignore`; the file is created on first wallet provisioning and treated like a private key.
- Workstation hygiene is the only mitigation here. Per Phase 0's accepted risks, this stays on the contributor's plate.

**Residual risk:** acknowledged. The Phase 5 cutover plan moves secrets to `fly secrets` and rotates keys; the dev box should never hold long-lived mainnet credentials.

## Threats and mitigations summary

| Threat | Mitigation |
|---|---|
| Lying RPC | Pydantic-validated `BlockSnapshot`; local-history reorg chain; `block_age_seconds_max` + `rpc_latency_ms_max` thresholds; circuit-breaker failover to a second provider; HTTPS-only |
| Hostile 0x quote | Pydantic-validated `LiquidityProbe`; multi-signal reasoning matrix; Tenderly simulation (Phase 2) |
| Malformed Anthropic output | Tool-use schema constraint; Pydantic-bounded `Decision`; cycle aborts on parse failure (safe default) |
| Audit DB tamper | Append-only SQLite triggers; per-row HMAC with separate key; `napg audit verify` |
| Wallet abuse via dev box | MPC keys in TEE; dust-capped testnet balance; safe address from env not reasoner; dry-run default |
| Prompt-cache poisoning | Cached block is static system prompt only; no user-influenced content cached |
| Secrets at rest | Gitignored; workstation hygiene (Phase 0 accepted risk) |

## Accepted risks

- **No active RPC cross-checking yet.** Failover gives availability but not cross-attestation. Closing this lands with the Phase 2 AgentShield pipeline that already has a "verify-or-die" hook for tx-simulation; we'll add a probe-level cross-check at the same time.
- **No signed policy/safe-address config.** Phase 2 introduces signed configs. Phase 1 ships with env-var configuration; a compromised dev box can rewrite the safe address.
- **Dust testnet balance is the practical cap.** Per-tx and daily caps land with AgentShield in Phase 2; Phase 1 relies on the wallet simply not having enough funds to do meaningful damage.
- **No backup of the local audit DB.** Phase 5 cutover lands encrypted off-box backups; until then, a hostile actor with `rm -f audit.db` can erase history (and we'd detect that on the next `audit verify`, but couldn't recover the prior content).
- **Rate-limiter defaults are unverified against every provider.** 5 req/s / burst 5 is the same default for the heartbeat (Sepolia RPC), Aerodrome (0x), and Morpho (Base mainnet RPC); it's comfortably under Alchemy's free tier and 0x's published limits, but isn't yet wired through env per upstream. Revisit during Phase 5 cutover with the chosen production providers, and split per-upstream if 0x's quota turns out to differ materially from the RPC providers'.

## Next phase delta

Phase 2 will add the AgentShield 4-stage validation pipeline (Intent Judge, Policy Validation, Tenderly Simulation, Honeypot Detection), a signed policy config, a kill-switch, and per-tx + daily spend caps. The Phase 2 threat-model file will document: what the validate-or-die pipeline does *not* cover, how the kill-switch fails (engaged but a tx already in flight), and what bypasses we accept.
