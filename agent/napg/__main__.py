"""Entry point for `python -m napg`. Phase 1: one-shot heartbeat for manual test 1.1."""

from __future__ import annotations

import argparse
import json
import sys

from napg import __version__
from napg.actions import migrate_to_safe
from napg.audit import AuditLog
from napg.audit import verify as audit_verify
from napg.config import Settings
from napg.monitor.aerodrome import AerodromeMonitor
from napg.monitor.morpho import MorphoMonitor
from napg.monitor.rpc import RpcHeartbeat
from napg.wallet import build_agent_wallet


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


def _cmd_wallet_show() -> int:
    settings = Settings()
    wallet = build_agent_wallet(settings)
    address = wallet.get_address()
    balance = wallet.get_balance()
    network = wallet.get_network()
    print(
        json.dumps(
            {
                "address": address,
                "balance_wei": str(balance),
                "network": getattr(network, "network_id", str(network)),
            },
            indent=2,
        )
    )
    return 0


def _cmd_migrate(args: argparse.Namespace) -> int:
    settings = Settings()
    if not settings.safe_contract_address:
        raise RuntimeError(
            "NAPG_SAFE_CONTRACT_ADDRESS is not set; migration target unknown."
        )
    if not settings.audit_hmac_key:
        raise RuntimeError(
            "NAPG_AUDIT_HMAC_KEY is not set; refusing to act without audit logging."
        )

    wallet = build_agent_wallet(settings)
    safe = args.to or settings.safe_contract_address
    value_wei = int(float(args.amount_eth) * 10**18)

    with AuditLog(settings.audit_db_path, hmac_key=settings.audit_hmac_key) as log:
        record = migrate_to_safe(
            wallet,
            safe,
            value_wei,
            dry_run=not args.execute,
            audit_log=log,
        )

    print(record.model_dump_json(indent=2))
    return 0


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

    wallet = sub.add_parser("wallet", help="CDP agent wallet tools")
    wallet_sub = wallet.add_subparsers(dest="wallet_command")
    wallet_sub.add_parser("show", help="print the agent's wallet address, balance, network")

    migrate = sub.add_parser(
        "migrate",
        help="execute or simulate move_to_safe_contract on the configured network",
    )
    migrate.add_argument(
        "--to",
        default=None,
        help="override NAPG_SAFE_CONTRACT_ADDRESS for this call",
    )
    migrate.add_argument(
        "--amount-eth",
        required=True,
        help="amount of native ETH to migrate (decimal string, e.g. 0.001)",
    )
    migrate.add_argument(
        "--execute",
        action="store_true",
        help="actually submit the transaction (default: dry-run only)",
    )

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
    if args.command == "wallet":
        if args.wallet_command == "show":
            return _cmd_wallet_show()
        wallet.print_help()
        return 0
    if args.command == "migrate":
        return _cmd_migrate(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
