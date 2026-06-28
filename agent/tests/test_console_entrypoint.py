"""Guard against napg/ module names that shadow third-party packages.

`napg/x402.py` once shadowed the third-party `x402` package: when the `napg`
console script ran with the `napg/` package dir on `sys.path[0]`,
coinbase_agentkit's `from x402.clients.base import ...` resolved to our
single-file module and crashed with "'x402' is not a package". pytest and
`python -m napg` were unaffected, so nothing caught it.

This test reproduces that exact `sys.path` condition deterministically — it runs
a subprocess whose cwd (and therefore `sys.path[0]`) is the `napg/` package dir,
then imports the thing coinbase_agentkit imports. If any future `napg/<name>.py`
shadows a third-party/stdlib top-level package the same way, this fails in CI
rather than only when an operator runs the console script.
"""

from __future__ import annotations

import os
import subprocess
import sys

import napg

_NAPG_DIR = os.path.dirname(os.path.abspath(napg.__file__))


def _run_with_napg_on_path(code: str) -> subprocess.CompletedProcess[str]:
    # For `python -c`, sys.path[0] is the cwd, so cwd=napg/ puts the package dir
    # first on the path -- the same shadowing condition the console script had.
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=_NAPG_DIR,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_napg_dir_does_not_shadow_third_party_x402() -> None:
    result = _run_with_napg_on_path("from x402.clients.base import decode_x_payment_response")
    assert result.returncode == 0, (
        "a module in napg/ shadows the third-party `x402` package when napg/ is on "
        "sys.path[0] (the console-script condition). Rename the offending napg/<name>.py.\n"
        f"stderr: {result.stderr}"
    )


def test_napg_console_entrypoint_starts() -> None:
    # The full entry-point import chain (napg.__main__ -> wallet -> coinbase_agentkit)
    # must load with napg/ on sys.path[0].
    result = _run_with_napg_on_path("from napg.__main__ import main")
    assert result.returncode == 0, (
        "napg.__main__ failed to import with napg/ on sys.path[0] -- likely a "
        f"top-level module-name collision.\nstderr: {result.stderr}"
    )
