"""Tests for the signed policy + denylist loaders and Stage 2 evaluator."""

from __future__ import annotations

from pathlib import Path

import pytest

from napg.agentshield.pipeline import TxIntent
from napg.agentshield.policy import (
    Denylist,
    PolicyConfig,
    generate_keypair,
    load_denylist,
    load_policy,
    sig_path_for,
    sign_file,
    verify_file,
)
from napg.agentshield.stages.policy import build_policy_stage
from napg.attribution import build_suffix
from napg.audit import AuditLog

# A pair of well-formed addresses for use across the tests.
ADDR_AGENT = "0x" + "a" * 40
ADDR_SAFE = "0x" + "b" * 40
ADDR_BAD = "0x" + "c" * 40
ADDR_BURN = "0x000000000000000000000000000000000000dead".lower()


def _write_keypair(tmp_path: Path) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    private_pem, public_pem = generate_keypair()
    private_path = tmp_path / "policy_signing_key.pem"
    public_path = tmp_path / "policy_public_key.pem"
    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    return private_path, public_path


def _write_signed(tmp_path: Path, name: str, body: str, private_key: Path) -> Path:
    path = tmp_path / name
    path.write_text(body)
    sign_file(path, private_key)
    return path


def test_load_policy_round_trips(tmp_path: Path) -> None:
    private_key, public_key = _write_keypair(tmp_path)
    body = """
max_value_wei_per_tx = 1000000000000000
daily_spend_cap_wei = 5000000000000000
token_allowlist = []
destination_allowlist = ["0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"]
"""
    config = _write_signed(tmp_path, "policy.toml", body, private_key)

    policy = load_policy(config, public_key)
    assert policy.max_value_wei_per_tx == 1000000000000000
    assert policy.daily_spend_cap_wei == 5000000000000000
    assert policy.destination_allowlist == ("0x" + "a" * 40,)


def test_load_denylist_round_trips(tmp_path: Path) -> None:
    private_key, public_key = _write_keypair(tmp_path)
    body = """
addresses = [
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
]
"""
    config = _write_signed(tmp_path, "denylist.toml", body, private_key)
    denylist = load_denylist(config, public_key)
    assert denylist.contains("0x0000000000000000000000000000000000000000") is True
    assert denylist.contains(ADDR_BURN.upper()) is True
    assert denylist.contains(ADDR_BAD) is False


def test_load_policy_rejects_missing_signature(tmp_path: Path) -> None:
    _, public_key = _write_keypair(tmp_path)
    config = tmp_path / "policy.toml"
    config.write_text("max_value_wei_per_tx = 1\ndaily_spend_cap_wei = 1\n")
    with pytest.raises(FileNotFoundError, match="signature file"):
        load_policy(config, public_key)


def test_load_policy_rejects_tampered_body(tmp_path: Path) -> None:
    private_key, public_key = _write_keypair(tmp_path)
    body = "max_value_wei_per_tx = 1\ndaily_spend_cap_wei = 1\n"
    config = _write_signed(tmp_path, "policy.toml", body, private_key)
    config.write_text(body + "# tampered\n")
    with pytest.raises(ValueError, match="did not verify"):
        load_policy(config, public_key)


def test_load_policy_rejects_wrong_public_key(tmp_path: Path) -> None:
    private_key, _ = _write_keypair(tmp_path)
    body = "max_value_wei_per_tx = 1\ndaily_spend_cap_wei = 1\n"
    config = _write_signed(tmp_path, "policy.toml", body, private_key)
    _, foreign_public = _write_keypair(tmp_path / "other")
    with pytest.raises(ValueError, match="did not verify"):
        load_policy(config, foreign_public)


def test_sign_file_writes_sig_path(tmp_path: Path) -> None:
    private_key, _ = _write_keypair(tmp_path)
    config = tmp_path / "policy.toml"
    config.write_text("max_value_wei_per_tx = 1\ndaily_spend_cap_wei = 1\n")
    sig_path = sign_file(config, private_key)
    assert sig_path == sig_path_for(config)
    assert sig_path.exists()
    assert sig_path.read_bytes()  # not empty


def test_verify_file_returns_true_on_match(tmp_path: Path) -> None:
    private_key, public_key = _write_keypair(tmp_path)
    config = _write_signed(
        tmp_path, "policy.toml", "max_value_wei_per_tx = 1\ndaily_spend_cap_wei = 1\n", private_key
    )
    assert verify_file(config, public_key) is True


def test_policy_rejects_bad_address(tmp_path: Path) -> None:
    private_key, public_key = _write_keypair(tmp_path)
    body = """
max_value_wei_per_tx = 1
daily_spend_cap_wei = 1
destination_allowlist = ["not-an-address"]
"""
    config = _write_signed(tmp_path, "policy.toml", body, private_key)
    with pytest.raises(ValueError):
        load_policy(config, public_key)


def test_denylist_normalizes_to_lowercase(tmp_path: Path) -> None:
    private_key, public_key = _write_keypair(tmp_path)
    body = """
addresses = ["0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"]
"""
    config = _write_signed(tmp_path, "denylist.toml", body, private_key)
    denylist = load_denylist(config, public_key)
    assert denylist.addresses == ("0x" + "a" * 40,)


# ---- Stage 2 (build_policy_stage) ----

DEFAULT_POLICY = PolicyConfig(
    max_value_wei_per_tx=1_000_000_000_000_000,  # 0.001 ETH
    daily_spend_cap_wei=5_000_000_000_000_000,  # 0.005 ETH
)
DEFAULT_DENYLIST = Denylist(addresses=(ADDR_BURN,))


def _intent(to: str = ADDR_SAFE, value_wei: int = 1, data: str = "0x") -> TxIntent:
    return TxIntent(
        action="migrate_to_safe",
        from_address=ADDR_AGENT,
        to_address=to,
        value_wei=value_wei,
        data=data,
    )


def test_stage_passes_when_all_checks_clean() -> None:
    stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST)
    result = stage(_intent(value_wei=100))
    assert result.passed is True


def test_stage_fails_when_destination_is_on_denylist() -> None:
    stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST)
    result = stage(_intent(to=ADDR_BURN))
    assert result.passed is False
    assert "denylist" in result.reason


def test_denylist_match_is_case_insensitive() -> None:
    stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST)
    result = stage(_intent(to=ADDR_BURN.upper()))
    assert result.passed is False


def test_stage_fails_when_destination_not_on_non_empty_allowlist() -> None:
    policy = PolicyConfig(
        max_value_wei_per_tx=1_000_000_000_000_000,
        daily_spend_cap_wei=5_000_000_000_000_000,
        destination_allowlist=(ADDR_SAFE,),
    )
    stage = build_policy_stage(policy=policy, denylist=DEFAULT_DENYLIST)
    result = stage(_intent(to=ADDR_BAD))
    assert result.passed is False
    assert "not on allowlist" in result.reason


def test_stage_passes_when_destination_on_allowlist() -> None:
    policy = PolicyConfig(
        max_value_wei_per_tx=1_000_000_000_000_000,
        daily_spend_cap_wei=5_000_000_000_000_000,
        destination_allowlist=(ADDR_SAFE,),
    )
    stage = build_policy_stage(policy=policy, denylist=DEFAULT_DENYLIST)
    result = stage(_intent(to=ADDR_SAFE))
    assert result.passed is True


def test_stage_fails_when_value_exceeds_per_tx_cap() -> None:
    stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST)
    result = stage(_intent(value_wei=DEFAULT_POLICY.max_value_wei_per_tx + 1))
    assert result.passed is False
    assert "per-tx cap" in result.reason


def test_stage_fails_on_non_native_calldata() -> None:
    stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST)
    result = stage(_intent(data="0xa9059cbb000000"))
    assert result.passed is False
    assert "non-native calldata" in result.reason


def test_stage_passes_native_transfer_tagged_with_builder_code() -> None:
    stage = build_policy_stage(
        policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST, builder_code="napg"
    )
    result = stage(_intent(data=build_suffix("napg")))
    assert result.passed is True


def test_stage_blocks_builder_code_suffix_when_none_configured() -> None:
    stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST)
    result = stage(_intent(data=build_suffix("napg")))
    assert result.passed is False
    assert "Builder Code" in result.reason


def test_stage_blocks_suffix_for_a_different_builder_code() -> None:
    stage = build_policy_stage(
        policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST, builder_code="napg"
    )
    result = stage(_intent(data=build_suffix("baseapp")))
    assert result.passed is False


def test_stage_blocks_contract_call_that_appends_our_suffix() -> None:
    """The security seam: arbitrary calldata ending in our suffix is still blocked."""
    stage = build_policy_stage(
        policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST, builder_code="napg"
    )
    sneaky = "0xa9059cbb" + build_suffix("napg").removeprefix("0x")
    result = stage(_intent(data=sneaky))
    assert result.passed is False


def test_stage_passes_when_no_audit_log_and_value_within_cap() -> None:
    """Without an audit log, daily-spend check is skipped (unit-test path)."""
    stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST)
    result = stage(_intent(value_wei=DEFAULT_POLICY.max_value_wei_per_tx))
    assert result.passed is True


def test_stage_fails_when_projected_daily_spend_exceeds_cap(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.db"
    with AuditLog(str(db_path), hmac_key="test-key") as log:
        # Land a non-dry-run action close to the cap.
        log.record(
            "action",
            {
                "action": "migrate_to_safe",
                "dry_run": False,
                "from_address": ADDR_AGENT,
                "to_address": ADDR_SAFE,
                "value_wei": DEFAULT_POLICY.daily_spend_cap_wei - 1,
                "observed_at": 0.0,
            },
        )
        stage = build_policy_stage(
            policy=DEFAULT_POLICY,
            denylist=DEFAULT_DENYLIST,
            audit_log=log,
        )
        # Projected = (cap - 1) + 2 = cap + 1 -> exceeds cap.
        result = stage(_intent(value_wei=2))

    assert result.passed is False
    assert "projected daily spend" in result.reason


def test_stage_ignores_dry_run_actions_in_daily_spend(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.db"
    with AuditLog(str(db_path), hmac_key="test-key") as log:
        log.record(
            "action",
            {
                "action": "migrate_to_safe",
                "dry_run": True,
                "from_address": ADDR_AGENT,
                "to_address": ADDR_SAFE,
                "value_wei": DEFAULT_POLICY.daily_spend_cap_wei * 1000,
                "observed_at": 0.0,
            },
        )
        stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST, audit_log=log)
        result = stage(_intent(value_wei=1))
    assert result.passed is True


def test_stage_ignores_actions_older_than_24h(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.db"
    with AuditLog(str(db_path), hmac_key="test-key") as log:
        # An action recorded 25 hours ago should drop out of the rolling window.
        old_ts = 1_700_000_000.0
        log.record(
            "action",
            {
                "action": "migrate_to_safe",
                "dry_run": False,
                "from_address": ADDR_AGENT,
                "to_address": ADDR_SAFE,
                "value_wei": DEFAULT_POLICY.daily_spend_cap_wei,
                "observed_at": old_ts,
            },
            at=old_ts,
        )
        # "Now" is 25h after that recording.
        now_provider = lambda: old_ts + 25 * 3600  # noqa: E731
        stage = build_policy_stage(
            policy=DEFAULT_POLICY,
            denylist=DEFAULT_DENYLIST,
            audit_log=log,
            now_provider=now_provider,
        )
        result = stage(_intent(value_wei=1))
    assert result.passed is True


def test_default_configs_load_after_signing(tmp_path: Path) -> None:
    """End-to-end smoke against the in-repo `agent/config/policy.toml`.

    Generates a fresh keypair in tmp_path, copies the shipped default
    configs across, signs them, then verifies both load. Catches schema
    drift between the shipped TOML and the Pydantic model.
    """
    private_key, public_key = _write_keypair(tmp_path)
    repo_root = Path(__file__).resolve().parents[2]
    for name in ("policy.toml", "denylist.toml"):
        src = repo_root / "config" / name
        dst = tmp_path / name
        dst.write_bytes(src.read_bytes())
        sign_file(dst, private_key)

    policy = load_policy(tmp_path / "policy.toml", public_key)
    denylist = load_denylist(tmp_path / "denylist.toml", public_key)

    assert policy.max_value_wei_per_tx > 0
    assert policy.daily_spend_cap_wei >= policy.max_value_wei_per_tx
    assert policy.max_slippage_bps == 50
    assert policy.max_simulation_age_seconds == 5
    assert policy.swap_token_allowlist == ()
    assert denylist.contains("0x0000000000000000000000000000000000000000") is True


# ---- Stage 2 swap slippage floor (Group E) ----


TOKEN_IN = "0x" + "cc" * 20
TOKEN_OUT = "0x" + "dd" * 20
# A policy that allows the test swap pair, so token-universe checks pass and we
# can exercise the gates that come after it.
SWAP_POLICY = PolicyConfig(
    max_value_wei_per_tx=1_000_000_000_000_000,
    daily_spend_cap_wei=5_000_000_000_000_000,
    swap_token_allowlist=(TOKEN_IN, TOKEN_OUT),
)


def _swap_intent(
    *,
    min_out_wei: int | None,
    quoted_out_wei: int | None,
    data: str = "0x",
    token_in: str | None = TOKEN_IN,
    token_out: str | None = TOKEN_OUT,
) -> TxIntent:
    return TxIntent(
        action="swap",
        from_address=ADDR_AGENT,
        to_address=ADDR_SAFE,
        value_wei=0,
        data=data,
        min_out_wei=min_out_wei,
        quoted_out_wei=quoted_out_wei,
        token_in=token_in,
        token_out=token_out,
    )


def test_swap_without_min_out_fails_closed() -> None:
    stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST)
    result = stage(_swap_intent(min_out_wei=None, quoted_out_wei=1_000_000))
    assert result.passed is False
    assert "slippage floor required" in result.reason


def test_swap_over_slippage_cap_fails_closed() -> None:
    stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST)
    # 60 bps implied vs 50 bps cap.
    result = stage(_swap_intent(min_out_wei=994_000, quoted_out_wei=1_000_000))
    assert result.passed is False
    assert "exceeds cap" in result.reason


def test_swap_min_out_above_quote_fails_closed() -> None:
    stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST)
    result = stage(_swap_intent(min_out_wei=1_000_001, quoted_out_wei=1_000_000))
    assert result.passed is False
    assert "nonsensical" in result.reason


def test_swap_blocked_when_no_token_allowlist() -> None:
    """Default (empty) swap allowlist blocks every swap that clears slippage —
    the transfer-only launch posture."""
    stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST)
    result = stage(_swap_intent(min_out_wei=995_000, quoted_out_wei=1_000_000))
    assert result.passed is False
    assert "no swap tokens allowlisted" in result.reason  # slippage passed, tokens blocked


def test_swap_blocked_when_token_not_on_allowlist() -> None:
    stage = build_policy_stage(policy=SWAP_POLICY, denylist=DEFAULT_DENYLIST)
    other = "0x" + "ee" * 20
    result = stage(_swap_intent(min_out_wei=995_000, quoted_out_wei=1_000_000, token_out=other))
    assert result.passed is False
    assert "not on the swap token allowlist" in result.reason


def test_swap_missing_tokens_fails_closed() -> None:
    stage = build_policy_stage(policy=SWAP_POLICY, denylist=DEFAULT_DENYLIST)
    result = stage(_swap_intent(min_out_wei=995_000, quoted_out_wei=1_000_000, token_in=None))
    assert result.passed is False
    assert "missing token_in/token_out" in result.reason


def test_swap_passes_floor_and_tokens_then_blocked_at_calldata() -> None:
    """A swap clearing both the slippage floor and the token universe still fails
    on its router calldata — proving both swap gates passed."""
    stage = build_policy_stage(policy=SWAP_POLICY, denylist=DEFAULT_DENYLIST)
    result = stage(_swap_intent(min_out_wei=995_000, quoted_out_wei=1_000_000, data="0x38ed1739"))
    assert result.passed is False
    assert "calldata" in result.reason  # not slippage, not token-universe


def test_native_transfer_ignores_swap_slippage_fields() -> None:
    stage = build_policy_stage(policy=DEFAULT_POLICY, denylist=DEFAULT_DENYLIST)
    # migrate_to_safe intent with no swap fields passes (slippage check skipped).
    result = stage(_intent(value_wei=100))
    assert result.passed is True


def test_is_swap_flag() -> None:
    assert _swap_intent(min_out_wei=1, quoted_out_wei=1).is_swap is True
    assert _intent().is_swap is False
