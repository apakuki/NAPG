# Manual tests — Phase 2 (AgentShield Security Layer)

These procedures verify the Phase 2 security layer end to end on a real
developer workstation. They are the human-driven complement to the unit +
integration test suites; their job is to catch issues the test suite cannot
reach (filesystem-level signing, real Tenderly round-trips, the kill-switch
acting on a real operator session).

Run them top-to-bottom after `uv sync` and before signing off on Phase 2.

---

## 2.1  Policy keypair generation

**Procedure**
1. `cd agent`
2. `uv run napg policy generate-key`

**Expected**
- A new private key at `~/.napg/policy_signing_key.pem` with chmod 600.
- The public key written to `agent/config/policy_public_key.pem`.
- Re-running the command refuses to clobber the existing key (exit code 2).

**Verifies:** the operator can bootstrap the signing key without leaking it
into the repo; the loader's expected files exist; the no-overwrite guard
works.

---

## 2.2  Sign + verify the shipped configs

**Procedure**
1. `uv run napg policy sign agent/config/policy.toml`
2. `uv run napg policy verify agent/config/policy.toml`
3. `uv run napg policy sign agent/config/denylist.toml`
4. `uv run napg policy verify agent/config/denylist.toml`

**Expected**
- Each `sign` writes a `.sig` next to the config.
- Each `verify` returns JSON with the verified path.
- Editing `policy.toml` (e.g. bump the per-tx cap) and re-running `verify`
  *without* re-signing fails with `policy config signature did not verify
  against the public key`.

**Verifies:** the round-trip works; tampering without the private key is
rejected at load time.

---

## 2.3  Denylist blocks a tx

**Procedure**
1. Edit `agent/config/denylist.toml` to add your safe-contract address.
2. `uv run napg policy sign agent/config/denylist.toml`
3. `uv run napg simulate sequencer-delay --execute` (or
   `uv run napg migrate --amount-eth 0.0001 --execute`).
4. Confirm the validator raises `ValidationFailure: AgentShield blocked tx:
   policy: destination on denylist: ...` and *no* `action` row is written.
5. Restore `denylist.toml`, re-sign, and confirm the cycle no longer blocks.

**Verifies:** Stage 2's denylist gate fires before any wallet method is
touched; the `validation` audit row carries the reason; restoring +
re-signing returns to a clean state.

---

## 2.4  Per-tx cap blocks a tx above the cap

**Procedure**
1. `uv run napg migrate --amount-eth 1.0 --execute` (where the live cap is
   0.001 ETH).

**Expected**
- `ValidationFailure: AgentShield blocked tx: policy: value_wei ... exceeds
  per-tx cap ...`
- One `validation` row in the audit DB with `passed=false`; no `action` row.
- `uv run napg audit verify` returns `ok=true`.

**Verifies:** Stage 2's per-tx cap is enforced live; the audit chain
survives a failed validation.

---

## 2.5  Kill-switch engages mid-cycle

**Procedure**
1. Start with `NAPG_KILL_SWITCH` unset.
2. `uv run napg simulate sequencer-delay` (dry-run) — confirm it completes
   a full cycle.
3. `export NAPG_KILL_SWITCH=1`
4. `uv run napg simulate sequencer-delay --execute`

**Expected**
- Step 4 raises `ValidationFailure: AgentShield: kill-switch engaged;
  signing blocked` *before* any Anthropic or Tenderly call. The
  `validation` audit row carries `kill_switch_engaged=true` and empty
  `stages`.
- `unset NAPG_KILL_SWITCH` followed by re-running step 4 proceeds normally.

**Verifies:** the env-var kill-switch acts on the next cycle without
restart; the audit row distinguishes a kill-switched failure from a stage
failure.

---

## 2.6  Live Tenderly simulation round-trip

**Procedure**
1. Confirm `TENDERLY_ACCOUNT_SLUG`, `TENDERLY_PROJECT_SLUG`, and
   `TENDERLY_ACCESS_KEY` are populated in `.env`.
2. `uv run python -c "from napg.config import Settings; from
   napg.agentshield.stages.tenderly import TenderlySimulator; from
   napg.agentshield.pipeline import TxIntent; s = Settings(); sim =
   TenderlySimulator(account_slug=s.tenderly_account_slug,
   project_slug=s.tenderly_project_slug,
   access_key=s.tenderly_access_key, network_id=84532); r =
   sim.simulate(TxIntent(action='migrate_to_safe', from_address='0x' +
   'a'*40, to_address=s.safe_contract_address, value_wei=1000));
   print(r['transaction']['status'], r['transaction']['gas_used'])"`

**Expected**
- A live `True 21000` (or similar) printed to stdout.
- The Tenderly dashboard shows no saved simulation (the call is ephemeral;
  `save=False`).

**Verifies:** Tenderly creds are valid; the response shape still matches
the parser; gas estimate falls within the native-transfer window.

---

## 2.7  Tenderly key scoping

**Procedure**
1. Open the Tenderly dashboard, navigate to API access keys.
2. Confirm the key in `.env` is scoped to a single project and uses the
   `Simulate-only` permission (or the narrowest read-only equivalent).
3. Rotate the key as part of Phase 2 sign-off (best practice; the live key
   has been used by AgentShield during phase build-out).

**Expected**
- The key permission scope is read-only / simulate-only.
- After rotation, the previous key is revoked; the new key is added to
  `.env` and a manual sim (`napg`-driven or curl) succeeds.

**Verifies:** the security checklist item on Tenderly key scoping; the
rotation runbook works.

---

## 2.8  CI invariant guard

**Procedure**
1. `uv run pytest tests/test_codebase_invariants.py -v`
2. Temporarily add `wallet.native_transfer(...)` to a non-allowlisted
   module (e.g. `napg/scenarios.py`) and re-run.

**Expected**
- Step 1 passes (two tests).
- Step 2 fails with `AssertionError: Wallet signing call outside
  napg.actions / napg.agentshield: napg/scenarios.py:NN: ...`
- After reverting the change, the suite passes again.

**Verifies:** the CI grep test actually catches a wallet-bypass violation;
it is not silently no-op.

---

## 2.9  End-to-end CLI: --execute under all stages clean

**Procedure**
1. Confirm `NAPG_KILL_SWITCH` is unset, `.env` is populated, configs are
   signed, denylist does *not* contain the safe address.
2. `uv run napg simulate sequencer-delay --amount-eth 0.0001 --execute`

**Expected**
- The four stages pass in order; one `validation` row + one `action` row
  land in the audit DB.
- Final `action` row contains the real Sepolia tx hash and `status:
  success`.
- `uv run napg audit verify` returns `ok=true`.

**Verifies:** the full Phase 2 pipeline runs end to end without regressing
any Phase 1 capability.

---

## Sign-off checklist

- [ ] All procedures completed.
- [ ] Phase 2 threat-model review filed
      ([docs/threat-models/phase-2.md](../threat-models/phase-2.md)).
- [ ] Security and Troubleshooting sections in
      [PLAN.md](../../PLAN.md#phase-2-wk-3-security-layer) reviewed.
- [ ] User has signed off.
