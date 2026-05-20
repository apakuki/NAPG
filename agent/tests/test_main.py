"""Tests for napg.__main__ — the CLI entry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from napg import __main__ as cli


def test_no_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "heartbeat" in out


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "napg" in capsys.readouterr().out


def test_heartbeat_subcommand_runs_one_tick(capsys: pytest.CaptureFixture[str]) -> None:
    fake_settings = MagicMock()
    fake_settings.active_rpc_urls.return_value = ("https://sepolia.example/rpc",)

    fake_result = MagicMock()
    fake_result.model_dump_json.return_value = '{"ok": true}'

    fake_pool = MagicMock()
    fake_pool.tick.return_value = fake_result

    with (
        patch.object(cli, "Settings", return_value=fake_settings),
        patch.object(cli, "RpcHeartbeat", return_value=MagicMock()) as heart_cls,
        patch.object(cli, "FailoverRpcHeartbeat", return_value=fake_pool) as pool_cls,
    ):
        rc = cli.main(["heartbeat"])

    assert rc == 0
    heart_cls.assert_called_once_with("https://sepolia.example/rpc")
    pool_cls.assert_called_once()
    fake_pool.tick.assert_called_once()
    assert '{"ok": true}' in capsys.readouterr().out


def test_heartbeat_subcommand_constructs_fallback_when_set() -> None:
    fake_settings = MagicMock()
    fake_settings.active_rpc_urls.return_value = (
        "https://primary.example/rpc",
        "https://fallback.example/rpc",
    )
    fake_pool = MagicMock()
    fake_pool.tick.return_value = MagicMock(model_dump_json=lambda **_: "{}")

    with (
        patch.object(cli, "Settings", return_value=fake_settings),
        patch.object(cli, "RpcHeartbeat", return_value=MagicMock()) as heart_cls,
        patch.object(cli, "FailoverRpcHeartbeat", return_value=fake_pool) as pool_cls,
    ):
        cli.main(["heartbeat"])

    assert heart_cls.call_count == 2
    pool_cls.assert_called_once()
    hearts_arg = pool_cls.call_args.args[0]
    assert len(hearts_arg) == 2


def test_aerodrome_subcommand_runs_one_tick(capsys: pytest.CaptureFixture[str]) -> None:
    fake_settings = MagicMock()
    fake_settings.zerox_api_key = "test-key"

    fake_result = MagicMock()
    fake_result.model_dump_json.return_value = '{"probe": true}'

    fake_monitor = MagicMock()
    fake_monitor.tick.return_value = fake_result

    with (
        patch.object(cli, "Settings", return_value=fake_settings),
        patch.object(cli, "AerodromeMonitor", return_value=fake_monitor) as monitor_cls,
    ):
        rc = cli.main(["aerodrome"])

    assert rc == 0
    monitor_cls.assert_called_once_with(api_key="test-key")
    fake_monitor.tick.assert_called_once()
    assert '{"probe": true}' in capsys.readouterr().out


def test_aerodrome_subcommand_errors_without_api_key() -> None:
    fake_settings = MagicMock()
    fake_settings.zerox_api_key = None

    with (
        patch.object(cli, "Settings", return_value=fake_settings),
        pytest.raises(RuntimeError, match="ZEROX_API_KEY"),
    ):
        cli.main(["aerodrome"])


def test_morpho_subcommand_runs_one_tick(capsys: pytest.CaptureFixture[str]) -> None:
    fake_settings = MagicMock()
    fake_settings.base_rpc_url = "https://base-mainnet.example/rpc"

    fake_result = MagicMock()
    fake_result.model_dump_json.return_value = '{"poll": true}'

    fake_monitor = MagicMock()
    fake_monitor.tick.return_value = fake_result

    with (
        patch.object(cli, "Settings", return_value=fake_settings),
        patch.object(cli, "MorphoMonitor", return_value=fake_monitor) as monitor_cls,
    ):
        rc = cli.main(["morpho"])

    assert rc == 0
    monitor_cls.assert_called_once_with("https://base-mainnet.example/rpc")
    fake_monitor.tick.assert_called_once()
    assert '{"poll": true}' in capsys.readouterr().out


def test_morpho_subcommand_errors_without_mainnet_rpc() -> None:
    fake_settings = MagicMock()
    fake_settings.base_rpc_url = None

    with (
        patch.object(cli, "Settings", return_value=fake_settings),
        pytest.raises(RuntimeError, match="BASE_RPC_URL"),
    ):
        cli.main(["morpho"])


def test_audit_verify_subcommand_exits_zero_when_ok(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_settings = MagicMock()
    fake_settings.audit_hmac_key = "key"
    fake_settings.audit_db_path = "./audit.db"

    fake_result = MagicMock()
    fake_result.ok = True
    fake_result.model_dump_json.return_value = '{"total_rows": 5, "tampered": []}'

    with (
        patch.object(cli, "Settings", return_value=fake_settings),
        patch.object(cli, "audit_verify", return_value=fake_result) as verify_fn,
    ):
        rc = cli.main(["audit", "verify"])

    assert rc == 0
    verify_fn.assert_called_once_with("./audit.db", "key")
    assert "tampered" in capsys.readouterr().out


def test_audit_verify_subcommand_exits_nonzero_on_tamper() -> None:
    fake_settings = MagicMock()
    fake_settings.audit_hmac_key = "key"
    fake_settings.audit_db_path = "./audit.db"

    fake_result = MagicMock()
    fake_result.ok = False
    fake_result.model_dump_json.return_value = '{"total_rows": 5, "tampered": [3]}'

    with (
        patch.object(cli, "Settings", return_value=fake_settings),
        patch.object(cli, "audit_verify", return_value=fake_result),
    ):
        rc = cli.main(["audit", "verify"])

    assert rc == 1


def test_audit_verify_subcommand_errors_without_key() -> None:
    fake_settings = MagicMock()
    fake_settings.audit_hmac_key = None

    with (
        patch.object(cli, "Settings", return_value=fake_settings),
        pytest.raises(RuntimeError, match="NAPG_AUDIT_HMAC_KEY"),
    ):
        cli.main(["audit", "verify"])


def test_audit_without_subcommand_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["audit"])
    assert rc == 0
    assert "verify" in capsys.readouterr().out


def test_wallet_show_subcommand_prints_address_balance_network(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_wallet = MagicMock()
    fake_wallet.get_address.return_value = "0x" + "11" * 20
    fake_wallet.get_balance.return_value = 12345
    fake_wallet.get_network.return_value = MagicMock(network_id="base-sepolia")

    with patch.object(cli, "build_agent_wallet", return_value=fake_wallet):
        rc = cli.main(["wallet", "show"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "0x" + "11" * 20 in out
    assert "base-sepolia" in out
    assert "12345" in out


def test_wallet_without_subcommand_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["wallet"])
    assert rc == 0
    assert "show" in capsys.readouterr().out


def test_migrate_dry_run_writes_audit_and_returns_zero(
    capsys: pytest.CaptureFixture[str], tmp_path
) -> None:
    fake_settings = MagicMock()
    fake_settings.safe_contract_address = "0x" + "22" * 20
    fake_settings.audit_hmac_key = "test-key"
    fake_settings.audit_db_path = str(tmp_path / "audit.db")

    fake_wallet = MagicMock()
    fake_wallet.get_address.return_value = "0x" + "11" * 20

    fake_record = MagicMock()
    fake_record.model_dump_json.return_value = '{"dry_run": true}'

    with (
        patch.object(cli, "Settings", return_value=fake_settings),
        patch.object(cli, "build_agent_wallet", return_value=fake_wallet),
        patch.object(cli, "migrate_to_safe", return_value=fake_record) as action,
    ):
        rc = cli.main(["migrate", "--amount-eth", "0.001"])

    assert rc == 0
    _, kwargs = action.call_args
    assert kwargs["dry_run"] is True
    assert '"dry_run": true' in capsys.readouterr().out


def test_migrate_execute_flips_dry_run_off(tmp_path) -> None:
    fake_settings = MagicMock()
    fake_settings.safe_contract_address = "0x" + "22" * 20
    fake_settings.audit_hmac_key = "test-key"
    fake_settings.audit_db_path = str(tmp_path / "audit.db")

    fake_record = MagicMock()
    fake_record.model_dump_json.return_value = "{}"

    with (
        patch.object(cli, "Settings", return_value=fake_settings),
        patch.object(cli, "build_agent_wallet", return_value=MagicMock()),
        patch.object(cli, "migrate_to_safe", return_value=fake_record) as action,
    ):
        cli.main(["migrate", "--amount-eth", "0.001", "--execute"])

    _, kwargs = action.call_args
    assert kwargs["dry_run"] is False


def test_migrate_requires_safe_address() -> None:
    fake_settings = MagicMock()
    fake_settings.safe_contract_address = None

    with (
        patch.object(cli, "Settings", return_value=fake_settings),
        pytest.raises(RuntimeError, match="NAPG_SAFE_CONTRACT_ADDRESS"),
    ):
        cli.main(["migrate", "--amount-eth", "0.001"])


def test_migrate_requires_audit_hmac_key() -> None:
    fake_settings = MagicMock()
    fake_settings.safe_contract_address = "0x" + "22" * 20
    fake_settings.audit_hmac_key = None

    with (
        patch.object(cli, "Settings", return_value=fake_settings),
        pytest.raises(RuntimeError, match="NAPG_AUDIT_HMAC_KEY"),
    ):
        cli.main(["migrate", "--amount-eth", "0.001"])
