"""Tests for the AgentShield Tenderly Simulation stage (Stage 3).

The Tenderly HTTP API is mocked; no network calls.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from napg.agentshield.pipeline import TxIntent
from napg.agentshield.stages.tenderly import (
    TenderlySimulator,
    build_tenderly_stage,
)

ADDR_AGENT = "0x" + "a" * 40
ADDR_SAFE = "0x" + "b" * 40


def _intent(value_wei: int = 1_000_000_000_000_000, data: str = "0x") -> TxIntent:
    return TxIntent(
        action="migrate_to_safe",
        from_address=ADDR_AGENT,
        to_address=ADDR_SAFE,
        value_wei=value_wei,
        data=data,
    )


def _ok_response(gas_used: int = 21_000) -> dict[str, Any]:
    return {
        "simulation": {"id": "sim-1", "status": True},
        "transaction": {
            "status": True,
            "gas_used": gas_used,
            "error_message": "",
        },
    }


def _revert_response(message: str = "execution reverted") -> dict[str, Any]:
    return {
        "simulation": {"id": "sim-2", "status": True},
        "transaction": {
            "status": False,
            "gas_used": 50_000,
            "error_message": message,
        },
    }


class _FakeSimulator:
    """Replaces `TenderlySimulator` in tests; configurable per-call behaviour."""

    def __init__(self, response: dict[str, Any] | None = None, raises: Exception | None = None):
        self._response = response
        self._raises = raises
        self.calls: list[TxIntent] = []

    def simulate(self, intent: TxIntent) -> dict[str, Any]:
        self.calls.append(intent)
        if self._raises is not None:
            raise self._raises
        assert self._response is not None
        return self._response


def test_passes_when_simulation_succeeds() -> None:
    sim = _FakeSimulator(_ok_response(gas_used=21_000))
    stage = build_tenderly_stage(
        account_slug="acct",
        project_slug="proj",
        access_key="key",
        network_id=84532,
        simulator=sim,
    )
    result = stage(_intent())
    assert result.passed is True
    assert result.details["gas_used"] == 21_000


def test_fails_when_simulation_engine_errors() -> None:
    """`simulation.status == false` means Tenderly itself failed."""
    sim = _FakeSimulator(
        {
            "simulation": {"id": "sim-3", "status": False},
            "transaction": {"status": False, "gas_used": 0, "error_message": "sim engine error"},
        }
    )
    stage = build_tenderly_stage(
        account_slug="acct",
        project_slug="proj",
        access_key="key",
        network_id=84532,
        simulator=sim,
    )
    result = stage(_intent())
    assert result.passed is False
    assert "simulation itself failed" in result.reason


def test_fails_when_simulated_tx_reverts() -> None:
    sim = _FakeSimulator(_revert_response("out of gas"))
    stage = build_tenderly_stage(
        account_slug="acct",
        project_slug="proj",
        access_key="key",
        network_id=84532,
        simulator=sim,
    )
    result = stage(_intent())
    assert result.passed is False
    assert "reverted" in result.reason
    assert "out of gas" in result.reason


def test_fails_on_native_transfer_gas_above_ceiling() -> None:
    """A 500k gas_used on a native transfer means we're not on the native-transfer path."""
    sim = _FakeSimulator(_ok_response(gas_used=500_000))
    stage = build_tenderly_stage(
        account_slug="acct",
        project_slug="proj",
        access_key="key",
        network_id=84532,
        simulator=sim,
    )
    result = stage(_intent(data="0x"))
    assert result.passed is False
    assert "gas_used 500000" in result.reason


def test_fails_on_native_transfer_gas_below_floor() -> None:
    sim = _FakeSimulator(_ok_response(gas_used=1000))
    stage = build_tenderly_stage(
        account_slug="acct",
        project_slug="proj",
        access_key="key",
        network_id=84532,
        simulator=sim,
    )
    result = stage(_intent(data="0x"))
    assert result.passed is False
    assert "outside native-transfer window" in result.reason


def test_skips_gas_window_check_for_non_native_calldata() -> None:
    """Non-native calldata is blocked by Stage 2 already; if we're here at all,
    Stage 3 doesn't second-guess gas usage outside the native-transfer window."""
    sim = _FakeSimulator(_ok_response(gas_used=500_000))
    stage = build_tenderly_stage(
        account_slug="acct",
        project_slug="proj",
        access_key="key",
        network_id=84532,
        simulator=sim,
    )
    result = stage(_intent(data="0xa9059cbb"))
    assert result.passed is True


def test_fails_on_transport_error() -> None:
    sim = _FakeSimulator(raises=httpx.ConnectError("connection refused"))
    stage = build_tenderly_stage(
        account_slug="acct",
        project_slug="proj",
        access_key="key",
        network_id=84532,
        simulator=sim,
    )
    result = stage(_intent())
    assert result.passed is False
    assert "transport failure" in result.reason


def test_simulator_requires_creds() -> None:
    with pytest.raises(ValueError, match="account_slug, project_slug, and access_key"):
        TenderlySimulator(
            account_slug="",
            project_slug="proj",
            access_key="key",
            network_id=84532,
        )


def test_simulator_posts_expected_payload() -> None:
    """End-to-end shape: the wire body matches Tenderly's `/simulate` expectations."""
    captured: dict[str, Any] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "simulation": {"id": "sim-7", "status": True},
                "transaction": {"status": True, "gas_used": 21_000, "error_message": ""},
            },
        )

    transport = httpx.MockTransport(_handler)
    client = httpx.Client(transport=transport)
    simulator = TenderlySimulator(
        account_slug="acct",
        project_slug="proj",
        access_key="sekret",
        network_id=84532,
        http=client,
    )
    raw = simulator.simulate(_intent())
    assert raw["simulation"]["status"] is True

    import json as _json

    assert captured["url"].endswith("/account/acct/project/proj/simulate")
    assert captured["headers"]["x-access-key"] == "sekret"
    parsed = _json.loads(captured["body"])
    assert parsed["network_id"] == "84532"
    assert parsed["from"] == ADDR_AGENT
    assert parsed["to"] == ADDR_SAFE
    assert parsed["value"] == "1000000000000000"
    assert parsed["input"] == "0x"


def test_simulator_raises_on_non_200() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad key")

    transport = httpx.MockTransport(_handler)
    client = httpx.Client(transport=transport)
    simulator = TenderlySimulator(
        account_slug="acct",
        project_slug="proj",
        access_key="bad",
        network_id=84532,
        http=client,
    )
    with pytest.raises(RuntimeError, match="HTTP 401"):
        simulator.simulate(_intent())
