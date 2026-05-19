"""Entry point for `python -m napg`. Phase 1: one-shot heartbeat for manual test 1.1."""

from __future__ import annotations

import argparse
import sys

from napg import __version__
from napg.audit import verify as audit_verify
from napg.config import Settings
from napg.monitor.aerodrome import AerodromeMonitor
from napg.monitor.morpho import MorphoMonitor
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


def _cmd_morpho() -> int:
    settings = Settings()
    if not settings.base_rpc_url:
        raise RuntimeError(
            "BASE_RPC_URL is not set; Morpho lives on Base mainnet so a mainnet RPC "
            "endpoint is required regardless of NAPG_NETWORK."
        )
    monitor = MorphoMonitor(settings.base_rpc_url)
    result = monitor.tick()
    print(result.model_dump_json(indent=2))
    return 0


def _cmd_audit_verify() -> int:
    settings = Settings()
    if not settings.audit_hmac_key:
        raise RuntimeError(
            "NAPG_AUDIT_HMAC_KEY is not set; verification cannot run without the HMAC key."
        )
    result = audit_verify(settings.audit_db_path, settings.audit_hmac_key)
    print(result.model_dump_json(indent=2))
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="napg", description="NetAssure Protocol Guardian")
    parser.add_argument("--version", action="version", version=f"napg {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("heartbeat", help="run one RPC heartbeat against the configured network")
    sub.add_parser("aerodrome", help="probe Aerodrome USDC/USDT liquidity via the 0x API")
    sub.add_parser("morpho", help="poll Morpho Blue lending markets on Base mainnet")

    audit = sub.add_parser("audit", help="audit-log tools")
    audit_sub = audit.add_subparsers(dest="audit_command")
    audit_sub.add_parser("verify", help="recompute every row HMAC and report tamper")

    args = parser.parse_args(argv)
    if args.command == "heartbeat":
        return _cmd_heartbeat()
    if args.command == "aerodrome":
        return _cmd_aerodrome()
    if args.command == "morpho":
        return _cmd_morpho()
    if args.command == "audit":
        if args.audit_command == "verify":
            return _cmd_audit_verify()
        audit.print_help()
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
