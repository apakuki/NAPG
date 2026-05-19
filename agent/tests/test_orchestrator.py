"""End-to-end pipeline tests for napg.orchestrator.

These are integration tests: real `evaluate()`, real `AuditLog`, real
`migrate_to_safe`. Only the two external boundaries are mocked — the
Anthropic SDK (so no network calls) and the CDP wallet provider (so no
testnet round-trips). That gives us the substep 9 milestone signal
("agent detects simulated sequencer delay and migrates testnet funds")
on a deterministic, hermetic test surface.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from napg.audit import AuditLog, verify
from napg.orchestrator import CycleReport, run_cycle
from napg.policy.breaches import BreachThresholds
from napg.reasoning import Reasoner
from napg.scenarios import sequencer_delay_heartbeat

HMAC_KEY = "test-hmac-key-do-not-use-in-prod"
AGENT_ADDR = "0x" + "11" * 20
SAFE_ADDR = "0x" + "22" * 20
TX_HASH = "0x" + "cd" * 32


def _anthropic_response(
    *,
    intent: str,
    rationale: str = "synthetic test response",
    supporting_breaches: tuple[str, ...] = (),
) -> SimpleNamespace:
    tool_block = SimpleNamespace(
        type="tool_use",
        name="submit_decision",
        input={
            "intent": intent,
            "rationale": rationale,
            "confidence": 0.95,
            "supporting_breaches": list(supporting_breaches),
        },
    )
    usage = SimpleNamespace(
        input_tokens=500,
        output_tokens=64,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=1500,
    )
    return SimpleNamespace(content=[tool_block], usage=usage, model="claude-opus-4-7")


def _mock_anthropic(response: SimpleNamespace) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = response
    return client


def _mock_wallet() -> MagicMock:
    wallet = MagicMock()
    wallet.get_address.return_value = AGENT_ADDR
    wallet.native_transfer.return_value = TX_HASH
    wallet.wait_for_transaction_receipt.return_value = SimpleNamespace(
        block_number=46_300_000, status=1
    )
    return wallet


def test_sequencer_delay_drives_migrate_dispatch(tmp_path: Path) -> None:
    """The headline Phase 1 milestone: stale-block + reorg input drives a
    migrate dispatch and produces a verifiable audit chain."""
    db = tmp_path / "audit.db"
    heartbeat = sequencer_delay_heartbeat(stale_seconds=600, now=1_716_000_000.0)
    client = _mock_anthropic(
        _anthropic_response(
            intent="migrate_to_safe",
            rationale="Reorg + stale block detected; chain integrity floor violated.",
            supporting_breaches=("reorg_is_breach", "block_age_seconds_max"),
        )
    )
    wallet = _mock_wallet()

    with AuditLog(db, hmac_key=HMAC_KEY) as log:
        reasoner = Reasoner(api_key="sk-test", client=client, audit_log=log)
        report = run_cycle(
            reasoner=reasoner,
            audit_log=log,
            thresholds=BreachThresholds(),
            heartbeat=heartbeat,
            wallet=wallet,
            safe_address=SAFE_ADDR,
            value_wei=1_000_000_000_000_000,
            dry_run=True,
            now=1_716_000_000.0,
        )

    assert isinstance(report, CycleReport)

    breach_rules = {b.rule for b in report.breaches}
    assert "reorg_is_breach" in breach_rules
    assert "block_age_seconds_max" in breach_rules
    assert "rpc_latency_ms_max" in breach_rules

    assert report.decision.intent == "migrate_to_safe"
    assert report.action is not None
    assert report.action.dry_run is True
    assert report.action.to_address == SAFE_ADDR
    assert report.action.value_wei == 1_000_000_000_000_000
    wallet.native_transfer.assert_not_called()

    result = verify(db, HMAC_KEY)
    assert result.ok
    assert result.total_rows == len(report.breaches) + 2


def test_audit_chain_ordering_breach_then_decision_then_action(tmp_path: Path) -> None:
    """Audit rows must appear in the order: breach... -> decision -> action."""
    db = tmp_path / "audit.db"
    heartbeat = sequencer_delay_heartbeat(stale_seconds=600, now=1_716_000_000.0)
    client = _mock_anthropic(
        _anthropic_response(intent="migrate_to_safe", supporting_breaches=("reorg_is_breach",))
    )

    with AuditLog(db, hmac_key=HMAC_KEY) as log:
        reasoner = Reasoner(api_key="sk-test", client=client, audit_log=log)
        run_cycle(
            reasoner=reasoner,
            audit_log=log,
            thresholds=BreachThresholds(),
            heartbeat=heartbeat,
            wallet=_mock_wallet(),
            safe_address=SAFE_ADDR,
            value_wei=1,
            dry_run=True,
            now=1_716_000_000.0,
        )
        kinds = [row.kind for row in log.iter_rows()]

    assert kinds[-2:] == ["decision", "action"]
    assert kinds[:-2] == ["breach"] * (len(kinds) - 2)


def test_hold_intent_writes_decision_but_no_action(tmp_path: Path) -> None:
    """No breaches -> hold -> no action row, but the decision still lands."""
    db = tmp_path / "audit.db"
    heartbeat = sequencer_delay_heartbeat(
        stale_seconds=0, include_reorg=False, latency_ms=100.0, now=1_716_000_000.0
    )
    client = _mock_anthropic(_anthropic_response(intent="hold"))

    with AuditLog(db, hmac_key=HMAC_KEY) as log:
        reasoner = Reasoner(api_key="sk-test", client=client, audit_log=log)
        report = run_cycle(
            reasoner=reasoner,
            audit_log=log,
            thresholds=BreachThresholds(),
            heartbeat=heartbeat,
            wallet=_mock_wallet(),
            safe_address=SAFE_ADDR,
            value_wei=1,
            dry_run=True,
            now=1_716_000_000.0,
        )
        kinds = [row.kind for row in log.iter_rows()]

    assert report.breaches == ()
    assert report.action is None
    assert kinds == ["decision"]


def test_pause_intent_writes_decision_but_no_action(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    heartbeat = sequencer_delay_heartbeat(
        stale_seconds=60, include_reorg=False, latency_ms=500.0, now=1_716_000_000.0
    )
    client = _mock_anthropic(
        _anthropic_response(
            intent="pause_for_investigation",
            supporting_breaches=("block_age_seconds_max",),
        )
    )

    with AuditLog(db, hmac_key=HMAC_KEY) as log:
        reasoner = Reasoner(api_key="sk-test", client=client, audit_log=log)
        report = run_cycle(
            reasoner=reasoner,
            audit_log=log,
            thresholds=BreachThresholds(),
            heartbeat=heartbeat,
            wallet=_mock_wallet(),
            safe_address=SAFE_ADDR,
            value_wei=1,
            dry_run=True,
            now=1_716_000_000.0,
        )

    assert report.action is None
    assert report.decision.intent == "pause_for_investigation"


def test_migrate_without_wallet_raises(tmp_path: Path) -> None:
    """If the reasoner picks migrate_to_safe but no wallet was supplied, the
    orchestrator refuses rather than silently dropping the action."""
    db = tmp_path / "audit.db"
    heartbeat = sequencer_delay_heartbeat(stale_seconds=600, now=1_716_000_000.0)
    client = _mock_anthropic(
        _anthropic_response(intent="migrate_to_safe", supporting_breaches=("reorg_is_breach",))
    )

    with AuditLog(db, hmac_key=HMAC_KEY) as log:
        reasoner = Reasoner(api_key="sk-test", client=client, audit_log=log)
        with pytest.raises(RuntimeError, match="wallet"):
            run_cycle(
                reasoner=reasoner,
                audit_log=log,
                thresholds=BreachThresholds(),
                heartbeat=heartbeat,
                wallet=None,
                safe_address=None,
                value_wei=1,
                dry_run=True,
                now=1_716_000_000.0,
            )


def test_executed_migrate_records_tx_hash(tmp_path: Path) -> None:
    """End-to-end with dry_run=False: action row carries the (mocked) tx hash."""
    db = tmp_path / "audit.db"
    heartbeat = sequencer_delay_heartbeat(stale_seconds=600, now=1_716_000_000.0)
    client = _mock_anthropic(
        _anthropic_response(intent="migrate_to_safe", supporting_breaches=("reorg_is_breach",))
    )
    wallet = _mock_wallet()

    with AuditLog(db, hmac_key=HMAC_KEY) as log:
        reasoner = Reasoner(api_key="sk-test", client=client, audit_log=log)
        report = run_cycle(
            reasoner=reasoner,
            audit_log=log,
            thresholds=BreachThresholds(),
            heartbeat=heartbeat,
            wallet=wallet,
            safe_address=SAFE_ADDR,
            value_wei=5_000,
            dry_run=False,
            now=1_716_000_000.0,
        )

    assert report.action is not None
    assert report.action.dry_run is False
    assert report.action.tx_hash == TX_HASH
    assert report.action.status == "success"
    wallet.native_transfer.assert_called_once_with(to=SAFE_ADDR, value="5000")
