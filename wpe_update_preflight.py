#!/usr/bin/env python3
"""Run preflight checks before plugin/theme update automation."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from wpe_updates_sync import (
    AUTO_STATUSES,
    fetch_all,
    find_accounts,
    load_config,
    normalize_key,
    wpe_auth_header,
)


NEXTGEN_SLUGS = {"nextgen-gallery", "nextgen-gallery-pro"}
NEXTGEN_NAMES = {"nextgen gallery", "nextgen gallery pro"}
PLUGIN_UPDATE_ERROR = "Plugin Update Error"
LOW_PHP_WARNING_BELOW = (8, 1)


@dataclass(frozen=True)
class EnvironmentInfo:
    account: str
    site: str
    environment: str
    install_id: str
    php_version: str


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_php_version(version: str) -> tuple[int, int] | None:
    parts = version.split(".")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return int(parts[0]), int(parts[1])


def php_warning(php_version: str) -> str:
    parsed = parse_php_version(php_version)
    if not parsed:
        return "Unknown PHP version; verify plugin compatibility manually"
    if parsed < LOW_PHP_WARNING_BELOW:
        return f"PHP {php_version} is older than 8.1; verify plugin compatibility before updating"
    return ""


def load_queue(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise RuntimeError(f"Update queue has no header row: {path}")
        return list(reader)


def load_plugin_inventory(path: Path | None) -> dict[str, set[str]]:
    if not path:
        return {}
    inventory: dict[str, set[str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise RuntimeError(f"Plugin inventory has no header row: {path}")
        for row in reader:
            environment = (
                row.get("environment")
                or row.get("Environment")
                or row.get("environment_name")
                or ""
            ).strip()
            if not environment:
                continue
            plugin = (
                row.get("plugin_slug")
                or row.get("slug")
                or row.get("plugin")
                or row.get("Plugin")
                or row.get("plugin_name")
                or ""
            ).strip()
            if plugin:
                inventory.setdefault(normalize_key(environment), set()).add(normalize_plugin(plugin))
    return inventory


def normalize_plugin(value: str) -> str:
    lowered = value.strip().lower()
    slugish = lowered.replace(" ", "-").replace("_", "-")
    if slugish in NEXTGEN_SLUGS:
        return slugish
    return lowered


def has_nextgen_pair(environment: str, inventory: dict[str, set[str]]) -> bool:
    plugins = inventory.get(normalize_key(environment), set())
    normalized_names = {plugin.replace("-", " ") for plugin in plugins}
    return (
        NEXTGEN_SLUGS.issubset(plugins)
        or NEXTGEN_NAMES.issubset(normalized_names)
    )


def fetch_environment_index(config_path: Path) -> dict[str, EnvironmentInfo]:
    config = load_config(config_path)
    headers = wpe_auth_header()
    accounts = find_accounts(config.accounts, fetch_all("/accounts", headers))
    index: dict[str, EnvironmentInfo] = {}

    for account_config in config.accounts:
        account = accounts[account_config.name]
        sites = fetch_all("/sites", headers, account_id=account["id"])
        for site in sites:
            for install in site.get("installs", []):
                environment = str(install.get("name", ""))
                if not environment:
                    continue
                index[normalize_key(environment)] = EnvironmentInfo(
                    account=account_config.name,
                    site=str(site.get("name", "")),
                    environment=environment,
                    install_id=str(install.get("id", "")),
                    php_version=str(install.get("php_version", "")),
                )
    return index


def latest_completed_backup(install_id: str) -> dict[str, Any] | None:
    if not install_id:
        return None
    headers = wpe_auth_header()
    backups = fetch_all(f"/installs/{install_id}/backups", headers)
    completed = [backup for backup in backups if backup.get("status") == "completed"]
    completed.sort(
        key=lambda backup: parse_datetime(str(backup.get("complete_time") or backup.get("create_time") or "")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return completed[0] if completed else None


def backup_ok(backup: dict[str, Any] | None, now: datetime, max_age_hours: int) -> tuple[bool, str, str]:
    if not backup:
        return False, "", "No completed backup found"
    completed_at = parse_datetime(str(backup.get("complete_time") or backup.get("create_time") or ""))
    if not completed_at:
        return False, "", "Latest completed backup has no usable timestamp"
    age = now - completed_at.astimezone(timezone.utc)
    timestamp = completed_at.isoformat()
    if age < timedelta(0):
        return False, timestamp, "Latest backup timestamp is in the future"
    if age > timedelta(hours=max_age_hours):
        return False, timestamp, f"Latest backup is older than {max_age_hours} hours"
    return True, timestamp, ""


def run_preflight(
    queue_path: Path,
    config_path: Path,
    out_path: Path,
    plugin_inventory_path: Path | None,
    max_backup_age_hours: int,
) -> list[dict[str, str]]:
    queue = load_queue(queue_path)
    environment_index = fetch_environment_index(config_path)
    plugin_inventory = load_plugin_inventory(plugin_inventory_path)
    now = datetime.now(timezone.utc)
    output_rows: list[dict[str, str]] = []

    for row in queue:
        environment = row.get("environment", "")
        info = environment_index.get(normalize_key(environment))
        latest_backup = latest_completed_backup(info.install_id) if info else None
        backup_passed, backup_time, backup_reason = backup_ok(latest_backup, now, max_backup_age_hours)
        php_version = info.php_version if info else ""
        php_reason = php_warning(php_version)
        nextgen_pair = has_nextgen_pair(environment, plugin_inventory)

        blockers: list[str] = []
        warnings: list[str] = []
        status_override = ""
        if not info:
            blockers.append("Environment not found in WP Engine API")
        if not backup_passed:
            blockers.append(backup_reason)
        if php_reason:
            warnings.append(php_reason)
        if nextgen_pair:
            blockers.append("NextGEN Gallery and NextGEN Gallery Pro are both installed")
            status_override = PLUGIN_UPDATE_ERROR

        output_rows.append(
            {
                **row,
                "install_id": info.install_id if info else "",
                "php_version": php_version,
                "backup_ok": str(backup_passed).lower(),
                "latest_backup_time": backup_time,
                "nextgen_pair_detected": str(nextgen_pair).lower(),
                "status_override": status_override,
                "preflight_passed": str(not blockers).lower(),
                "preflight_blockers": "; ".join(blockers),
                "preflight_warnings": "; ".join(warnings),
            }
        )

    write_preflight(out_path, output_rows)
    return output_rows


def write_preflight(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "account",
        "site",
        "environment",
        "status",
        "update_plugins",
        "update_themes",
        "update_wordpress",
        "requires_review",
        "reason",
        "install_id",
        "php_version",
        "backup_ok",
        "latest_backup_time",
        "nextgen_pair_detected",
        "status_override",
        "preflight_passed",
        "preflight_blockers",
        "preflight_warnings",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict[str, str]]) -> None:
    blocked = [row for row in rows if row["preflight_passed"] != "true"]
    overrides = [row for row in rows if row["status_override"]]
    print(f"Preflight rows: {len(rows)}")
    print(f"Passed: {len(rows) - len(blocked)}")
    print(f"Blocked: {len(blocked)}")
    print(f"Status overrides: {len(overrides)}")
    for row in blocked[:10]:
        print(f"- {row['account']} / {row['environment']}: {row['preflight_blockers']}")
    if len(blocked) > 10:
        print(f"... {len(blocked) - 10} more blocked")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", default="update-queue.csv", type=Path)
    parser.add_argument("--config", default="config.yml", type=Path)
    parser.add_argument("--out", default="update-preflight.csv", type=Path)
    parser.add_argument(
        "--plugin-inventory",
        type=Path,
        help="Optional CSV with environment and plugin/plugin_slug columns for plugin-specific checks.",
    )
    parser.add_argument("--max-backup-age-hours", default=36, type=int)
    args = parser.parse_args()

    rows = run_preflight(
        queue_path=args.queue,
        config_path=args.config,
        out_path=args.out,
        plugin_inventory_path=args.plugin_inventory,
        max_backup_age_hours=args.max_backup_age_hours,
    )
    print_summary(rows)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
