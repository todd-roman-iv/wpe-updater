#!/usr/bin/env python3
"""Run GitHub Actions entry points for the WP Engine sheet automation."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]


def run(args: list[str]) -> None:
    print("+ " + " ".join(args))
    subprocess.run(args, cwd=BASE, check=True)


def optional_args(account: str, environment: str) -> list[str]:
    args: list[str] = []
    if account:
        args.extend(["--account", account])
    if environment:
        args.extend(["--environment", environment])
    return args


def refresh_environments(config: Path) -> None:
    run([sys.executable, "wpe_updates_sync.py", "--config", str(config)])


def scan_dns(config: Path, account: str, environment: str) -> None:
    out = BASE / "dns-elsewhere-statuses.csv"
    run(
        [
            sys.executable,
            "wpe_dns_statuses.py",
            "--config",
            str(config),
            "--out",
            str(out),
            *optional_args(account, environment),
        ]
    )
    run(
        [
            sys.executable,
            "wpe_updates_sync.py",
            "--config",
            str(config),
            "--updates-csv",
            str(out),
            "--status-only",
        ]
    )


def prepare_updates(config: Path, max_backup_age_hours: int) -> None:
    run([sys.executable, "export_sheet_statuses.py"])
    run(
        [
            sys.executable,
            "wpe_update_queue.py",
            "--statuses-csv",
            "sheet-current-statuses.csv",
            "--out",
            "update-queue.csv",
        ]
    )
    run(
        [
            sys.executable,
            "wpe_update_preflight.py",
            "--queue",
            "update-queue.csv",
            "--config",
            str(config),
            "--out",
            "update-preflight.csv",
            "--max-backup-age-hours",
            str(max_backup_age_hours),
        ]
    )
    run(
        [
            sys.executable,
            "wpe_updates_sync.py",
            "--config",
            str(config),
            "--updates-csv",
            "update-preflight.csv",
            "--status-only",
        ]
    )


def dry_run_updates(
    config: Path,
    account: str,
    environment: str,
    include_critical: bool,
    max_backup_age_hours: int,
) -> None:
    prepare_updates(config, max_backup_age_hours)
    args = [
        sys.executable,
        "wpe_update_runner.py",
        "--preflight",
        "update-preflight.csv",
        "--log",
        "update-run-log.csv",
        "--completion-csv",
        "update-complete-statuses.csv",
    ]
    if account:
        args.extend(["--account", account])
    if environment:
        args.extend(["--environment", environment])
    if include_critical:
        args.append("--include-critical")
    run(args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--config", default="config.github.yml", type=Path)
    parser.add_argument("--account", default="")
    parser.add_argument("--environment", default="")
    parser.add_argument("--include-critical", action="store_true")
    parser.add_argument("--max-backup-age-hours", default=36, type=int)
    args = parser.parse_args()

    if args.task == "refresh_environments":
        refresh_environments(args.config)
    elif args.task == "scan_dns":
        scan_dns(args.config, args.account, args.environment)
    elif args.task == "prepare_updates":
        prepare_updates(args.config, args.max_backup_age_hours)
    elif args.task == "dry_run_updates":
        dry_run_updates(
            args.config,
            args.account,
            args.environment,
            args.include_critical,
            args.max_backup_age_hours,
        )
    else:
        raise RuntimeError(f"Unsupported task: {args.task}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
