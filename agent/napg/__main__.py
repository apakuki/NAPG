"""Entry point for `python -m napg`. Phase 1: one-shot heartbeat for manual test 1.1."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from napg import __version__
from napg.actions import migrate_to_safe
from napg.agentshield.policy import (
    default_private_key_path,
    default_public_key_path,
    generate_keypair,
    sign_file,
    verify_file,
)
from napg.agentshield.production import build_production_validator
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
from napg.reporting import (
    AssuranceReport,
    default_reporting_public_key_path,
    generate_seed_hex,
    verify_report,
)
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
        validator = build_production_validator(settings, audit_log=log) if args.execute else None
        record = migrate_to_safe(
            wallet,
            safe,
            value_wei,
            dry_run=not args.execute,
            audit_log=log,
            validator=validator,
            rationale=(
                "operator-initiated migration via `napg migrate --execute`"
                if args.execute
                else "operator dry-run via `napg migrate`"
            ),
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
        validator = build_production_validator(settings, audit_log=log) if args.execute else None
        report = run_cycle(
            reasoner=reasoner,
            audit_log=log,
            thresholds=thresholds,
            heartbeat=heartbeat,
            wallet=wallet,
            safe_address=settings.safe_contract_address,
            value_wei=value_wei,
            dry_run=not args.execute,
            validator=validator,
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


def _cmd_policy_generate_key() -> int:
    """Create an Ed25519 keypair: private at ~/.napg/, public at agent/config/.

    The private key never lands in the repo. The public key gets written
    into `agent/config/policy_public_key.pem` so the loader has something
    to verify against. Idempotent only if no key exists at the target path;
    re-running with an existing key refuses to clobber it.
    """
    private_path = default_private_key_path()
    public_path = default_public_key_path()
    if private_path.exists():
        print(
            f"refusing to overwrite existing private key at {private_path}; "
            "remove it manually first if you are intentionally rotating.",
            file=sys.stderr,
        )
        return 2
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    private_pem, public_pem = generate_keypair()
    private_path.write_bytes(private_pem)
    private_path.chmod(0o600)
    public_path.write_bytes(public_pem)
    print(
        json.dumps(
            {
                "private_key_path": str(private_path),
                "public_key_path": str(public_path),
                "note": (
                    "Commit the public key. Keep the private key out of git "
                    "(it is under ~/.napg/, which is outside the repo)."
                ),
            },
            indent=2,
        )
    )
    return 0


def _cmd_policy_sign(args: argparse.Namespace) -> int:
    """Sign a config file with the configured private key. Writes <path>.sig."""
    config_path = Path(args.path)
    private_path = Path(args.private_key) if args.private_key else default_private_key_path()
    sig_path = sign_file(config_path, private_path)
    print(json.dumps({"signed": str(config_path), "signature": str(sig_path)}, indent=2))
    return 0


def _cmd_policy_verify(args: argparse.Namespace) -> int:
    """Verify a config file's signature against the configured public key."""
    config_path = Path(args.path)
    public_path = Path(args.public_key) if args.public_key else default_public_key_path()
    verify_file(config_path, public_path)
    print(json.dumps({"verified": str(config_path), "public_key": str(public_path)}, indent=2))
    return 0


def _cmd_report_generate_key(args: argparse.Namespace) -> int:
    """Generate the dedicated Assurance Report signing keypair (Ed25519).

    Prints the seed for NAPG_REPORTING_SIGNING_KEY (secret; never commit it) and
    writes the public key to agent/config/reporting_public_key.pem (publish it so
    consumers can verify reports). Refuses to clobber an existing public key.
    """
    public_path = Path(args.public_key) if args.public_key else default_reporting_public_key_path()
    if public_path.exists():
        print(
            f"refusing to overwrite existing public key at {public_path}; "
            "remove it manually first if you are intentionally rotating.",
            file=sys.stderr,
        )
        return 2
    seed_hex, public_pem = generate_seed_hex()
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_bytes(public_pem)
    print(
        json.dumps(
            {
                "reporting_signing_key": seed_hex,
                "public_key_path": str(public_path),
                "note": (
                    "Set NAPG_REPORTING_SIGNING_KEY to the seed above (secret; "
                    "never commit it). Commit/publish the public key so consumers "
                    "can verify reports."
                ),
            },
            indent=2,
        )
    )
    return 0


def _cmd_report_verify(args: argparse.Namespace) -> int:
    """Verify an Assurance Report's signature against the published public key."""
    report = AssuranceReport.model_validate_json(Path(args.path).read_text(encoding="utf-8"))
    public_path = Path(args.public_key) if args.public_key else default_reporting_public_key_path()
    verify_report(report, public_path.read_bytes())
    print(
        json.dumps(
            {"verified": str(args.path), "kid": report.kid, "public_key": str(public_path)},
            indent=2,
        )
    )
    return 0


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

    policy = sub.add_parser(
        "policy",
        help="AgentShield policy + denylist key management (Ed25519)",
    )
    policy_sub = policy.add_subparsers(dest="policy_command")
    policy_sub.add_parser(
        "generate-key",
        help="generate ~/.napg/policy_signing_key.pem and agent/config/policy_public_key.pem",
    )
    policy_sign = policy_sub.add_parser("sign", help="sign a config file; writes <path>.sig")
    policy_sign.add_argument("path", help="config file to sign (e.g. agent/config/policy.toml)")
    policy_sign.add_argument(
        "--private-key",
        default=None,
        help="override ~/.napg/policy_signing_key.pem (default)",
    )
    policy_verify = policy_sub.add_parser(
        "verify", help="verify a config file's signature against the committed public key"
    )
    policy_verify.add_argument("path", help="config file to verify")
    policy_verify.add_argument(
        "--public-key",
        default=None,
        help="override agent/config/policy_public_key.pem (default)",
    )

    report = sub.add_parser(
        "report",
        help="Assurance Report signing-key management (Ed25519)",
    )
    report_sub = report.add_subparsers(dest="report_command")
    report_genkey = report_sub.add_parser(
        "generate-key",
        help="generate the reporting keypair; print the seed, write the public key",
    )
    report_genkey.add_argument(
        "--public-key",
        default=None,
        help="override agent/config/reporting_public_key.pem (default)",
    )
    report_verify = report_sub.add_parser(
        "verify", help="verify an Assurance Report's signature against the public key"
    )
    report_verify.add_argument("path", help="report JSON file to verify")
    report_verify.add_argument(
        "--public-key",
        default=None,
        help="override agent/config/reporting_public_key.pem (default)",
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
    if args.command == "policy":
        if args.policy_command == "generate-key":
            return _cmd_policy_generate_key()
        if args.policy_command == "sign":
            return _cmd_policy_sign(args)
        if args.policy_command == "verify":
            return _cmd_policy_verify(args)
        policy.print_help()
        return 0
    if args.command == "report":
        if args.report_command == "generate-key":
            return _cmd_report_generate_key(args)
        if args.report_command == "verify":
            return _cmd_report_verify(args)
        report.print_help()
        return 0
    if args.command == "serve":
        return _cmd_serve(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
