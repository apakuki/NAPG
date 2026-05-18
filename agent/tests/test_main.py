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
    fake_settings.active_rpc_url.return_value = "https://sepolia.example/rpc"

    fake_result = MagicMock()
    fake_result.model_dump_json.return_value = '{"ok": true}'

    fake_heart = MagicMock()
    fake_heart.tick.return_value = fake_result

    with (
        patch.object(cli, "Settings", return_value=fake_settings),
        patch.object(cli, "RpcHeartbeat", return_value=fake_heart) as heart_cls,
    ):
        rc = cli.main(["heartbeat"])

    assert rc == 0
    heart_cls.assert_called_once_with("https://sepolia.example/rpc")
    fake_heart.tick.assert_called_once()
    assert '{"ok": true}' in capsys.readouterr().out
