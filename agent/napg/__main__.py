"""Entry point for `python -m napg`. Phase 1: one-shot heartbeat for manual test 1.1."""

from __future__ import annotations

import argparse
import sys

from napg import __version__
from napg.config import Settings
from napg.monitor.rpc import RpcHeartbeat


def _cmd_heartbeat() -> int:
    settings = Settings()
    rpc_url = settings.active_rpc_url()
    heart = RpcHeartbeat(rpc_url)
    result = heart.tick()
    print(result.model_dump_json(indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="napg", description="NetAssure Protocol Guardian")
    parser.add_argument("--version", action="version", version=f"napg {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("heartbeat", help="run one RPC heartbeat against the configured network")

    args = parser.parse_args(argv)
    if args.command == "heartbeat":
        return _cmd_heartbeat()

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
