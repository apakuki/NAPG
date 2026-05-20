"""Stage 4 — Honeypot Detection.

For every tx that interacts with a token, AgentShield runs a BUY-then-
SELL probe via Tenderly simulation: simulate a small purchase of the
token from the agent wallet, then simulate selling that same amount
back. If either leg reverts or the sell-output is wildly off the
buy-input, the token is flagged as a honeypot and the stage fails.

Phase 2 action surface is `migrate_to_safe` (native ETH transfer to a
pre-pinned safe address). Native transfers have no "target token" —
the only asset moving is ETH itself, and ETH is not a candidate for
honeypot logic. For these intents Stage 4 returns a trivial-pass with
a note documenting why; the real BUY-then-SELL machinery activates
when token-handling actions land (Phase 4 x402 / swap surfaces).

The `HoneypotCache` lands in this commit even though it has nothing
to cache yet — having the contract in place means the future token-
aware code path drops in without re-shaping the stage's external API,
and the cache-invalidation-by-codeHash unit tests document the
contract we will honour once it matters.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from napg.agentshield.pipeline import StageResult, TxIntent
from napg.agentshield.stages.tenderly import TenderlySimulator

_NATIVE_TRANSFER_CALLDATA = "0x"


@dataclass
class HoneypotCache:
    """Per-token cache of honeypot verdicts, keyed by (address, codeHash).

    Invariants:
    - A verdict is keyed by the *current* `codeHash` of the contract.
      Any code redeploy or proxy upgrade changes the hash, invalidating
      the entry implicitly.
    - Entries are never updated in place; a code change yields a fresh
      key. Old keys can age out via `evict_older_than` (call from a
      janitor task — Phase 5 wiring).
    """

    _entries: dict[tuple[str, str], bool] = field(default_factory=dict)

    def get(self, address: str, code_hash: str) -> bool | None:
        return self._entries.get((address.lower(), code_hash.lower()))

    def set(self, address: str, code_hash: str, is_safe: bool) -> None:
        self._entries[(address.lower(), code_hash.lower())] = is_safe

    def evict_older_than(self, addresses_with_new_code_hash: dict[str, str]) -> int:
        """Drop entries whose stored code_hash no longer matches the live one.

        Returns the number of entries dropped. The caller passes a fresh
        snapshot of `{address: current_code_hash}`; anything in the cache
        keyed off a different code_hash for those addresses is removed.
        """
        normalized = {addr.lower(): h.lower() for addr, h in addresses_with_new_code_hash.items()}
        dropped = 0
        for key in list(self._entries):
            addr, stored_hash = key
            live_hash = normalized.get(addr)
            if live_hash is not None and live_hash != stored_hash:
                del self._entries[key]
                dropped += 1
        return dropped

    def __len__(self) -> int:
        return len(self._entries)


def build_honeypot_stage(
    *,
    simulator: TenderlySimulator | None = None,
    cache: HoneypotCache | None = None,
) -> Callable[[TxIntent], StageResult]:
    """Return a Stage 4 callable.

    For native transfers Stage 4 passes trivially — there is no target
    token. For non-native calldata Stage 4 fails closed with an
    explanatory reason; the live BUY-then-SELL machinery lands when
    token-handling actions are introduced.

    `simulator` and `cache` are accepted now so callers can wire them
    in once token actions exist, without changing the stage's external
    shape. Phase 2 callers pass nothing.
    """
    _ = simulator  # reserved for the token-aware path
    bound_cache = cache if cache is not None else HoneypotCache()

    def _stage(intent: TxIntent) -> StageResult:
        if intent.data == _NATIVE_TRANSFER_CALLDATA:
            return StageResult(
                stage="honeypot",
                passed=True,
                reason="native transfer; no target token to probe",
                details={"cache_size": len(bound_cache)},
            )
        # Non-native calldata is blocked by Stage 2 today; if we ever reach
        # Stage 4 with calldata it means Stage 2's gate has loosened and the
        # BUY-then-SELL probe must be implemented. Fail closed until then.
        return StageResult(
            stage="honeypot",
            passed=False,
            reason=(
                "non-native calldata not yet supported by Stage 4; "
                "BUY-then-SELL probe lands with token-action substep"
            ),
        )

    return _stage


__all__ = ["HoneypotCache", "build_honeypot_stage"]
