"""Invariants the codebase must maintain.

These are codebase-level guards (not behavioural unit tests) that fail the
build if the structural rules AgentShield depends on are violated.
"""

from __future__ import annotations

import re
from pathlib import Path

_AGENT_SRC = Path(__file__).resolve().parents[1] / "napg"

# Methods on `CdpEvmWalletProvider` that touch signing / submission. Anything
# in production code that calls one of these must do so via the AgentShield
# pipeline (`napg.agentshield.validate_or_die`) — meaning the call site must
# live in `napg.actions` (which calls the validator before signing) or inside
# the agentshield package itself.
_WALLET_METHOD_PATTERNS = [
    re.compile(r"\.native_transfer\("),
    re.compile(r"\.send_transaction\("),
    re.compile(r"\.invoke\("),
    re.compile(r"\.sign_message\("),
    re.compile(r"\.sign_typed_data\("),
    re.compile(r"\.wait_for_transaction_receipt\("),
]

# Files (relative to `napg/`) that are allowed to call wallet methods. The
# CDP wallet bootstrap (`wallet.py`) is also allowed — it constructs the
# wallet but does not invoke signing methods on it.
_ALLOWED_FILES = {
    "actions.py",
    "wallet.py",
}

# Subpackages whose entire contents are allowed.
_ALLOWED_PREFIXES = ("agentshield/",)


def _is_allowed(rel_path: str) -> bool:
    if rel_path in _ALLOWED_FILES:
        return True
    return any(rel_path.startswith(prefix) for prefix in _ALLOWED_PREFIXES)


def test_no_wallet_method_calls_outside_actions_or_agentshield() -> None:
    """Wallet signing methods may only be called from `napg.actions` (which
    routes through AgentShield's `validate_or_die`) or from inside the
    `napg.agentshield` package itself. Any other call site is a bypass.
    """
    violations: list[str] = []
    for path in sorted(_AGENT_SRC.rglob("*.py")):
        rel_path = str(path.relative_to(_AGENT_SRC))
        if _is_allowed(rel_path):
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            # Skip comments / docstrings that just mention the methods.
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            for pattern in _WALLET_METHOD_PATTERNS:
                if pattern.search(line):
                    violations.append(f"napg/{rel_path}:{line_no}: {line.strip()}")
    assert not violations, (
        "Wallet signing call outside napg.actions / napg.agentshield "
        "(every signing path must route through validate_or_die):\n" + "\n".join(violations)
    )


def test_actions_imports_agentshield() -> None:
    """`napg.actions` must import from `napg.agentshield` — the seam between
    the action layer and the validator. Without this import the action
    cannot call the validator at all.
    """
    text = (_AGENT_SRC / "actions.py").read_text(encoding="utf-8")
    assert "from napg.agentshield" in text, (
        "napg.actions must import from napg.agentshield to use validate_or_die"
    )
