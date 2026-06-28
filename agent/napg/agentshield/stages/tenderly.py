"""Stage 3 — Tenderly Simulation.

Posts the proposed transaction to Tenderly's `/simulate` endpoint, parses
the response, and fails closed on any of:

- Tenderly itself reported an error (`simulation.status == false`).
- The simulated tx reverted (`transaction.status == false` or
  `transaction.error_message` is non-empty).
- Gas used is outside the expected window for the tx kind (defends
  against contract-call shapes accidentally landing on the
  native-transfer path).

State-diff parsing in detail (verifying sender balance dropped by
exactly `value + gas`, receiver balance rose by exactly `value`) is
deferred to Phase 5 — the response shape is rich and the in-Phase
mitigation (sender = MPC wallet, receiver constrained by env-pinned
safe address, dust cap from Stage 2) already bounds blast radius.
Documented as an accepted risk in `docs/threat-models/phase-2.md`.

Tenderly access key is expected to be read-only (Simulate-only),
scoped to a single project, and rotated when this phase ships per
the security checklist. The wrapping code never logs or persists
the key.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from napg.agentshield.pipeline import StageResult, TxIntent

_DEFAULT_GAS_LIMIT = 100_000
_NATIVE_TRANSFER_GAS_CEILING = 200_000
_NATIVE_TRANSFER_GAS_FLOOR = 21_000


class TenderlySimulator:
    """Wraps the Tenderly simulate POST. Injectable HTTP client for tests."""

    def __init__(
        self,
        *,
        account_slug: str,
        project_slug: str,
        access_key: str,
        network_id: int,
        http: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not account_slug or not project_slug or not access_key:
            raise ValueError(
                "Tenderly simulator requires account_slug, project_slug, and access_key"
            )
        self._url = (
            f"https://api.tenderly.co/api/v1/account/{account_slug}/project/{project_slug}/simulate"
        )
        self._headers = {"X-Access-Key": access_key, "Content-Type": "application/json"}
        self._network_id = str(network_id)
        self._http = http if http is not None else httpx.Client(timeout=timeout)

    def simulate(self, intent: TxIntent) -> dict[str, Any]:
        body = {
            "network_id": self._network_id,
            "from": intent.from_address,
            "to": intent.to_address,
            "value": str(intent.value_wei),
            "input": intent.data,
            "gas": _DEFAULT_GAS_LIMIT,
            "save": False,
            "save_if_fails": False,
        }
        response = self._http.post(self._url, json=body, headers=self._headers)
        if response.status_code != 200:
            raise RuntimeError(
                f"Tenderly /simulate returned HTTP {response.status_code}: {response.text[:200]}"
            )
        return response.json()


class TenderlyOutcome(BaseModel):
    """Subset of the Tenderly response the stage actually reads."""

    model_config = ConfigDict(frozen=True)

    simulation_status: bool
    transaction_status: bool
    error_message: str
    gas_used: int


def _parse_outcome(response: dict[str, Any]) -> TenderlyOutcome:
    """Pull only the fields the stage decides on; ignore the rest."""
    simulation = response.get("simulation") or {}
    transaction = response.get("transaction") or {}
    return TenderlyOutcome(
        simulation_status=bool(simulation.get("status", False)),
        transaction_status=bool(transaction.get("status", False)),
        error_message=str(transaction.get("error_message") or ""),
        gas_used=int(transaction.get("gas_used") or 0),
    )


def build_tenderly_stage(
    *,
    account_slug: str,
    project_slug: str,
    access_key: str,
    network_id: int,
    simulator: TenderlySimulator | None = None,
    http: httpx.Client | None = None,
) -> Callable[[TxIntent], StageResult]:
    """Return a Stage 3 callable bound to a Tenderly project.

    `simulator` is injectable so tests run against a fake without
    touching the network. The default constructs a real one with the
    supplied creds.
    """
    sim = (
        simulator
        if simulator is not None
        else TenderlySimulator(
            account_slug=account_slug,
            project_slug=project_slug,
            access_key=access_key,
            network_id=network_id,
            http=http,
        )
    )

    def _stage(intent: TxIntent) -> StageResult:
        try:
            raw = sim.simulate(intent)
        except (httpx.HTTPError, RuntimeError) as exc:
            return StageResult(
                stage="tenderly",
                passed=False,
                reason=f"tenderly simulation transport failure: {type(exc).__name__}: {exc}",
            )
        outcome = _parse_outcome(raw)

        if not outcome.simulation_status:
            return StageResult(
                stage="tenderly",
                passed=False,
                reason="tenderly simulation itself failed (simulation.status=false)",
                details=outcome.model_dump(),
            )
        if not outcome.transaction_status:
            return StageResult(
                stage="tenderly",
                passed=False,
                reason=(f"simulated tx reverted: {outcome.error_message or 'no error message'}"),
                details=outcome.model_dump(),
            )
        if intent.data == "0x" and not (
            _NATIVE_TRANSFER_GAS_FLOOR <= outcome.gas_used <= _NATIVE_TRANSFER_GAS_CEILING
        ):
            return StageResult(
                stage="tenderly",
                passed=False,
                reason=(
                    f"gas_used {outcome.gas_used} outside native-transfer window "
                    f"[{_NATIVE_TRANSFER_GAS_FLOOR}, {_NATIVE_TRANSFER_GAS_CEILING}]"
                ),
                details=outcome.model_dump(),
            )

        return StageResult(
            stage="tenderly",
            passed=True,
            reason="tenderly simulation passed",
            # `simulated_at` lets the signer enforce the simulation-freshness
            # gate (is_simulation_fresh) before committing — the market can move
            # between sim and inclusion.
            details={**outcome.model_dump(), "simulated_at": time.time()},
        )

    return _stage


def is_simulation_fresh(
    stage_details: dict[str, Any], max_age_seconds: float, *, now: float | None = None
) -> bool:
    """True if a passing Stage 3 result is recent enough to sign against.

    Fail-closed: a result without a `simulated_at` stamp is treated as not fresh.
    The signer calls this with `policy.max_simulation_age_seconds` immediately
    before requesting a signature; a stale result must be re-simulated, not signed.
    """
    simulated_at = stage_details.get("simulated_at")
    if simulated_at is None:
        return False
    current = now if now is not None else time.time()
    return current - float(simulated_at) <= max_age_seconds


__all__ = [
    "TenderlyOutcome",
    "TenderlySimulator",
    "build_tenderly_stage",
    "is_simulation_fresh",
]
