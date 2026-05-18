"""Entry point for `python -m napg`. Phase 1: one-shot heartbeat for manual test 1.1."""

from __future__ import annotations

import argparse
import sys

from napg import __version__
from napg.config import Settings
from napg.monitor.aerodrome import AerodromeMonitor
from napg.monitor.rpc import RpcHeartbeat


def _cmd_heartbeat() -> int:
    settings = Settings()
    rpc_url = settings.active_rpc_url()
    heart = RpcHeartbeat(rpc_url)
    result = heart.tick()
    print(result.model_dump_json(indent=2))
    return 0


def _cmd_aerodrome() -> int:
    settings = Settings()
    if not settings.zerox_api_key:
        raise RuntimeError("ZEROX_API_KEY is not set; populate .env before running this probe.")
    monitor = AerodromeMonitor(api_key=settings.zerox_api_key)
    result = monitor.tick()
    print(result.model_dump_json(indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="napg", description="NetAssure Protocol Guardian")
    parser.add_argument("--version", action="version", version=f"napg {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("heartbeat", help="run one RPC heartbeat against the configured network")
    sub.add_parser("aerodrome", help="probe Aerodrome USDC/USDbC liquidity via the 0x API")

    args = parser.parse_args(argv)
    if args.command == "heartbeat":
        return _cmd_heartbeat()
    if args.command == "aerodrome":
        return _cmd_aerodrome()

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
