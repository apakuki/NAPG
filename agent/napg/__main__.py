"""Entry point for `python -m napg`. Phase 1: one-shot heartbeat for manual test 1.1."""

from __future__ import annotations

import argparse
import json
import sys

from napg import __version__
from napg.actions import migrate_to_safe
from napg.api import create_app
from napg.audit import AuditLog
from napg.audit import verify as audit_verify
from napg.config import Settings
from napg.monitor.aerodrome import AerodromeMonitor
from napg.monitor.morpho import MorphoMonitor
from napg.monitor.resilience import FailoverRpcHeartbeat
from napg.monitor.rpc import RpcHeartbeat
from napg.orchestrator import run_cycle
from napg.policy.breaches import load_thresholds
from napg.reasoning import Reasoner
from napg.scenarios import sequencer_delay_heartbeat
from napg.wallet import build_agent_wallet


def _cmd_heartbeat() -> int:
    settings = Settings()
    urls = settings.active_rpc_urls()
    hearts = [RpcHeartbeat(u) for u in urls]
    pool = FailoverRpcHeartbeat(hearts)
    result = pool.tick()
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
        raise RuntimeError("NAPG_SAFE_CONTRACT_ADDRESS is not set; migration target unknown.")
    if not settings.audit_hmac_key:
        raise RuntimeError("NAPG_AUDIT_HMAC_KEY is not set; refusing to act without audit logging.")

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


def _cmd_simulate_sequencer_delay(args: argparse.Namespace) -> int:
    """Run one orchestrator cycle on a synthesized sequencer-delay heartbeat.

    Lives in the CLI because every dependency it touches (Anthropic SDK,
    CDP wallet, audit DB) is already wired by the surrounding commands.
    The scenario itself is a pure function in `napg.scenarios`.
    """
    settings = Settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; reasoning cannot run.")
    if not settings.audit_hmac_key:
        raise RuntimeError("NAPG_AUDIT_HMAC_KEY is not set; refusing to act without audit logging.")
    if not settings.safe_contract_address:
        raise RuntimeError("NAPG_SAFE_CONTRACT_ADDRESS is not set; migration target unknown.")

    heartbeat = sequencer_delay_heartbeat(
        stale_seconds=args.stale_seconds,
        include_reorg=not args.no_reorg,
    )
    value_wei = int(float(args.amount_eth) * 10**18)
    thresholds = load_thresholds()

    with AuditLog(settings.audit_db_path, hmac_key=settings.audit_hmac_key) as log:
        log.record(
            "scenario",
            {
                "name": "sequencer_delay",
                "stale_seconds": args.stale_seconds,
                "include_reorg": not args.no_reorg,
                "execute": bool(args.execute),
            },
        )
        wallet = build_agent_wallet(settings) if args.execute else _DryRunWallet(settings)
        reasoner = Reasoner(api_key=settings.anthropic_api_key, audit_log=log)
        report = run_cycle(
            reasoner=reasoner,
            audit_log=log,
            thresholds=thresholds,
            heartbeat=heartbeat,
            wallet=wallet,
            safe_address=settings.safe_contract_address,
            value_wei=value_wei,
            dry_run=not args.execute,
        )

    print(report.model_dump_json(indent=2))
    return 0


class _DryRunWallet:
    """Stand-in wallet used when the simulator runs without --execute.

    `migrate_to_safe(dry_run=True)` never calls `native_transfer` or
    `wait_for_transaction_receipt`, so a real CDP wallet (with its API
    round-trips and gas budget) is unnecessary for the simulation path.
    Only `get_address` is invoked.
    """

    def __init__(self, settings: Settings) -> None:
        self._address = settings.cdp_agent_address or ("0x" + "00" * 20)

    def get_address(self) -> str:
        return self._address

    def native_transfer(self, to: str, value: str) -> str:  # pragma: no cover - dry-run guard
        raise RuntimeError("_DryRunWallet cannot submit transactions; rerun with --execute")

    def wait_for_transaction_receipt(self, tx_hash: str) -> object:  # pragma: no cover
        raise RuntimeError("_DryRunWallet has no receipts; rerun with --execute")


def _cmd_serve(args: argparse.Namespace) -> int:
    """Run the FastAPI app via uvicorn. Imported lazily so tests don't need uvicorn."""
    import uvicorn  # lazy: keeps uvicorn out of the import path for `napg` consumers

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
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

    simulate = sub.add_parser(
        "simulate",
        help="run an end-to-end pipeline cycle on a synthesized scenario",
    )
    simulate_sub = simulate.add_subparsers(dest="scenario")
    seq_delay = simulate_sub.add_parser(
        "sequencer-delay",
        help="synthesize a stale-block + reorg heartbeat and run one cycle",
    )
    seq_delay.add_argument(
        "--stale-seconds",
        type=int,
        default=600,
        help="how many seconds old the synthetic block should be (default: 600)",
    )
    seq_delay.add_argument(
        "--no-reorg",
        action="store_true",
        help="omit the reorg flag (default: include it)",
    )
    seq_delay.add_argument(
        "--amount-eth",
        default="0.001",
        help="amount of native ETH to migrate if the cycle picks migrate_to_safe",
    )
    seq_delay.add_argument(
        "--execute",
        action="store_true",
        help="actually submit the migration tx if chosen (default: dry-run only)",
    )

    serve = sub.add_parser(
        "serve",
        help="run the FastAPI read endpoint that powers the Service Assurance Dashboard",
    )
    serve.add_argument("--host", default="127.0.0.1", help="bind host (default: 127.0.0.1)")
    serve.add_argument("--port", type=int, default=8000, help="bind port (default: 8000)")
    serve.add_argument(
        "--log-level",
        default="info",
        choices=("debug", "info", "warning", "error"),
        help="uvicorn log level (default: info)",
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
    if args.command == "simulate":
        if args.scenario == "sequencer-delay":
            return _cmd_simulate_sequencer_delay(args)
        simulate.print_help()
        return 0
    if args.command == "serve":
        return _cmd_serve(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
