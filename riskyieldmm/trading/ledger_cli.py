"""Command-line verification for a V3 governance ledger."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from .canonical import canonical_json_text, strict_json_loads
from .ledger import SignedLedgerCheckpoint, V3GovernanceLedger
from .ledger_signing import Ed25519CheckpointVerifier


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="riskyieldmm-ledger",
        description="Verify a RiskYieldMM V3 governance receipt ledger.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="run full ledger verification")
    verify.add_argument("database", type=Path)
    verify.add_argument(
        "--checkpoint",
        type=Path,
        help="externally stored signed checkpoint JSON",
    )
    verify.add_argument(
        "--public-key-hex",
        help="32-byte Ed25519 public key for --checkpoint",
    )
    return parser


def _trusted_inputs(
    checkpoint_path: Path | None,
    public_key_hex: str | None,
) -> tuple[SignedLedgerCheckpoint | None, Ed25519CheckpointVerifier | None]:
    if checkpoint_path is None and public_key_hex is None:
        return None, None
    if checkpoint_path is None or public_key_hex is None:
        raise ValueError("--checkpoint and --public-key-hex must be supplied together")
    payload = strict_json_loads(checkpoint_path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError("checkpoint JSON must contain an object")
    checkpoint = SignedLedgerCheckpoint.from_mapping(payload)
    try:
        public_bytes = bytes.fromhex(public_key_hex)
    except ValueError as exc:
        raise ValueError("--public-key-hex is not valid hexadecimal") from exc
    verifier = Ed25519CheckpointVerifier.from_public_bytes(
        public_bytes,
        key_id=checkpoint.key_id,
    )
    return checkpoint, verifier


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        checkpoint, verifier = _trusted_inputs(
            args.checkpoint,
            args.public_key_hex,
        )
        with V3GovernanceLedger.open_read_only(args.database) as ledger:
            report = ledger.verify(
                trusted_checkpoint=checkpoint,
                verifier=verifier,
            )
        print(canonical_json_text(report.as_dict()))
        return 0
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"ledger verification failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
