#!/usr/bin/env python3
"""Guarded runner for WP Engine plugin/theme update automation.

The browser-clicking implementation is intentionally separated from queue and
preflight validation. This script enforces scope, preflight, critical-review
flags, and completion status output.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


COMPLETION_STATUS = "Update Complete"


@dataclass(frozen=True)
class RunnerItem:
    account: str
    site: str
    environment: str
    status: str
    update_plugins: bool
    update_themes: bool
    requires_review: bool
    preflight_passed: bool
    preflight_blockers: str


def parse_bool(value: str) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y"}


def load_preflight(path: Path) -> list[RunnerItem]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise RuntimeError(f"Preflight file has no header row: {path}")
        items: list[RunnerItem] = []
        for row in reader:
            environment = (row.get("environment") or "").strip()
            if not environment:
                continue
            items.append(
                RunnerItem(
                    account=(row.get("account") or "").strip(),
                    site=(row.get("site") or "").strip(),
                    environment=environment,
                    status=(row.get("status") or "").strip(),
                    update_plugins=parse_bool(row.get("update_plugins", "")),
                    update_themes=parse_bool(row.get("update_themes", "")),
                    requires_review=parse_bool(row.get("requires_review", "")),
                    preflight_passed=parse_bool(row.get("preflight_passed", "")),
                    preflight_blockers=(row.get("preflight_blockers") or "").strip(),
                )
            )
    return items


def filter_items(
    items: list[RunnerItem],
    account: str | None,
    environment: str | None,
    include_critical: bool,
) -> list[RunnerItem]:
    filtered = items
    if account:
        filtered = [item for item in filtered if item.account == account]
    if environment:
        filtered = [item for item in filtered if item.environment == environment]
    if not include_critical:
        filtered = [item for item in filtered if not item.requires_review]
    return filtered


def validate_apply(items: list[RunnerItem], apply: bool) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items:
        action = "would_update" if not apply else "blocked"
        result = "dry_run" if not apply else "blocked"
        message = ""
        if not item.preflight_passed:
            action = "blocked"
            result = "blocked"
            message = item.preflight_blockers or "Preflight did not pass"
        elif apply:
            action = "pending_browser_runner"
            result = "not_implemented"
            message = "Browser update clicker is not implemented in this CLI runner yet"

        rows.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "account": item.account,
                "site": item.site,
                "environment": item.environment,
                "status": item.status,
                "update_plugins": str(item.update_plugins).lower(),
                "update_themes": str(item.update_themes).lower(),
                "action": action,
                "result": result,
                "message": message,
            }
        )
    return rows


def write_log(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "timestamp",
                "account",
                "site",
                "environment",
                "status",
                "update_plugins",
                "update_themes",
                "action",
                "result",
                "message",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_completion_statuses(path: Path, log_rows: list[dict[str, str]]) -> int:
    completed = [row for row in log_rows if row["result"] == "complete"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["account", "site", "environment", "status"],
        )
        writer.writeheader()
        for row in completed:
            writer.writerow(
                {
                    "account": row["account"],
                    "site": row["site"],
                    "environment": row["environment"],
                    "status": COMPLETION_STATUS,
                }
            )
    return len(completed)


def print_summary(rows: list[dict[str, str]], apply: bool) -> None:
    print(f"Runner mode: {'apply' if apply else 'dry-run'}")
    print(f"Rows considered: {len(rows)}")
    print(f"Blocked: {sum(1 for row in rows if row['result'] == 'blocked')}")
    print(f"Would update: {sum(1 for row in rows if row['action'] == 'would_update')}")
    print(f"Completed: {sum(1 for row in rows if row['result'] == 'complete')}")
    for row in rows[:10]:
        print(f"- {row['account']} / {row['environment']}: {row['action']} {row['message']}".rstrip())
    if len(rows) > 10:
        print(f"... {len(rows) - 10} more")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", default="update-preflight.csv", type=Path)
    parser.add_argument("--account")
    parser.add_argument("--environment")
    parser.add_argument("--include-critical", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--log", default="update-run-log.csv", type=Path)
    parser.add_argument("--completion-csv", default="update-complete-statuses.csv", type=Path)
    args = parser.parse_args()

    if args.apply and not (args.account or args.environment):
        raise RuntimeError("--apply requires --account or --environment to limit scope.")

    items = filter_items(
        load_preflight(args.preflight),
        account=args.account,
        environment=args.environment,
        include_critical=args.include_critical,
    )
    log_rows = validate_apply(items, apply=args.apply)
    write_log(args.log, log_rows)
    completed = write_completion_statuses(args.completion_csv, log_rows)
    print_summary(log_rows, apply=args.apply)
    print(f"Wrote {args.log}")
    print(f"Wrote {args.completion_csv} with {completed} completed environment(s)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)
