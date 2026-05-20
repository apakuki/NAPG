"""Unit tests for napg.actions — wallet provider is mocked end-to-end."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from napg.actions import ActionRecord, migrate_to_safe
from napg.agentshield.pipeline import StageResult, TxIntent, ValidationResult
from napg.audit import AuditLog, verify

HMAC_KEY = "test-hmac-key-do-not-use-in-prod"
AGENT = "0x" + "11" * 20
SAFE = "0x" + "22" * 20


def _passing_validator(intent: TxIntent) -> ValidationResult:
    """Stub validator that always passes — for tests that don't exercise AgentShield."""
    stages = tuple(
        StageResult(stage=name, passed=True)
        for name in ("intent_judge", "policy", "tenderly", "honeypot")
    )
    return ValidationResult(intent=intent, stages=stages, passed=True)


def _wallet(tx_hash: str = "0x" + "ab" * 32, block_number: int = 46_300_000) -> MagicMock:
    wallet = MagicMock()
    wallet.get_address.return_value = AGENT
    wallet.native_transfer.return_value = tx_hash
    wallet.wait_for_transaction_receipt.return_value = SimpleNamespace(
        block_number=block_number,
        status=1,
    )
    return wallet


def test_dry_run_does_not_submit_tx() -> None:
    wallet = _wallet()

    record = migrate_to_safe(wallet, SAFE, 1_000_000)

    assert record.dry_run is True
    assert record.tx_hash is None
    assert record.block_number is None
    assert record.from_address == AGENT
    assert record.to_address == SAFE
    assert record.value_wei == 1_000_000
    wallet.native_transfer.assert_not_called()
    wallet.wait_for_transaction_receipt.assert_not_called()


def test_execute_path_submits_and_captures_receipt() -> None:
    wallet = _wallet(tx_hash="0x" + "cd" * 32, block_number=46_400_000)

    # 5_000 wei = 5e-15 ETH — pick a value whose Decimal conversion is exact.
    record = migrate_to_safe(wallet, SAFE, 5_000, dry_run=False, validator=_passing_validator)

    wallet.native_transfer.assert_called_once()
    kwargs = wallet.native_transfer.call_args.kwargs
    assert kwargs["to"] == SAFE
    assert isinstance(kwargs["value"], Decimal)
    assert kwargs["value"] == Decimal("5000") / Decimal(10**18)
    wallet.wait_for_transaction_receipt.assert_called_once_with("0x" + "cd" * 32)
    assert record.dry_run is False
    assert record.tx_hash == "0x" + "cd" * 32
    assert record.block_number == 46_400_000
    assert record.status == "success"


def test_execute_converts_wei_to_whole_ether_decimal() -> None:
    """Regression: passing wei-as-string made the CDP API read 10^18 too much."""
    wallet = _wallet()

    # 1 ETH = 10**18 wei. The Decimal handed to the wallet must equal 1.
    migrate_to_safe(wallet, SAFE, 10**18, dry_run=False, validator=_passing_validator)
    value = wallet.native_transfer.call_args.kwargs["value"]
    assert value == Decimal("1")


def test_receipt_status_zero_reports_failure() -> None:
    wallet = _wallet()
    wallet.wait_for_transaction_receipt.return_value = SimpleNamespace(block_number=1, status=0)

    record = migrate_to_safe(wallet, SAFE, 1, dry_run=False, validator=_passing_validator)
    assert record.status == "failure"


def test_receipt_camelcase_field_supported() -> None:
    """Some Web3-style receipts use blockNumber; accept both."""
    wallet = _wallet()
    wallet.wait_for_transaction_receipt.return_value = SimpleNamespace(blockNumber=99, status=1)

    record = migrate_to_safe(wallet, SAFE, 1, dry_run=False, validator=_passing_validator)
    assert record.block_number == 99


def test_invalid_safe_address_rejected() -> None:
    wallet = _wallet()
    with pytest.raises(ValueError, match="safe_address"):
        migrate_to_safe(wallet, "not-an-address", 100)


def test_negative_value_rejected() -> None:
    wallet = _wallet()
    with pytest.raises(ValueError, match="value_wei"):
        migrate_to_safe(wallet, SAFE, -1)


def test_dry_run_writes_audit_row(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    wallet = _wallet()

    with AuditLog(db, hmac_key=HMAC_KEY) as log:
        migrate_to_safe(wallet, SAFE, 12_345, audit_log=log)
        rows = list(log.iter_rows())

    assert len(rows) == 1
    assert rows[0].kind == "action"
    assert rows[0].payload["dry_run"] is True
    assert rows[0].payload["value_wei"] == 12_345
    assert rows[0].payload["tx_hash"] is None


def test_executed_action_writes_audit_row(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    wallet = _wallet(tx_hash="0x" + "ef" * 32, block_number=46_500_000)

    with AuditLog(db, hmac_key=HMAC_KEY) as log:
        record = migrate_to_safe(
            wallet,
            SAFE,
            100,
            dry_run=False,
            audit_log=log,
            validator=_passing_validator,
        )
        rows = list(log.iter_rows())

    assert len(rows) == 1
    payload = rows[0].payload
    assert payload["dry_run"] is False
    assert payload["tx_hash"] == "0x" + "ef" * 32
    assert payload["block_number"] == 46_500_000
    assert payload["status"] == "success"
    assert record.tx_hash == payload["tx_hash"]


def test_action_row_passes_hmac_verification(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    wallet = _wallet()

    with AuditLog(db, hmac_key=HMAC_KEY) as log:
        migrate_to_safe(wallet, SAFE, 1, dry_run=False, audit_log=log, validator=_passing_validator)

    result = verify(db, HMAC_KEY)
    assert result.ok is True


def test_action_record_is_json_safe() -> None:
    record = ActionRecord(
        action="migrate_to_safe",
        dry_run=False,
        from_address=AGENT,
        to_address=SAFE,
        value_wei=42,
        tx_hash="0x" + "00" * 32,
        block_number=1,
        status="success",
        observed_at=1.0,
    )
    dumped = record.model_dump_json()
    assert "migrate_to_safe" in dumped
    assert "0x" + "00" * 32 in dumped
