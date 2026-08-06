#!/usr/bin/env python3
"""Build a guarded plugin/theme update queue from WP Engine status data."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path


PLUGIN_STATUSES = {"Critical Update Needed", "Plugins Outdated"}
WORDPRESS_STATUSES = {"WP Outdated"}
STATUS_PRIORITY = {
    "Critical Update Needed": 0,
    "Plugins Outdated": 1,
    "WP Outdated": 2,
}


@dataclass(frozen=True)
class UpdateQueueItem:
    account: str
    site: str
    environment: str
    status: str
    update_plugins: bool
    update_themes: bool
    update_wordpress: bool
    requires_review: bool
    reason: str


def truthy_count(value: str) -> int:
    value = (value or "").strip()
    if not value:
        return 0
    for token in value.replace(",", " ").split():
        if token.isdigit():
            return int(token)
    return 1 if value.lower() not in {"0", "false", "no", "none", "n/a", "na"} else 0


def build_queue_item(row: dict[str, str]) -> UpdateQueueItem | None:
    status = (row.get("status") or row.get("Status") or "").strip()
    account = (row.get("account") or row.get("Account") or "").strip()
    site = (row.get("site") or row.get("Site") or row.get("site_name") or "").strip()
    environment = (
        row.get("environment")
        or row.get("Environment")
        or row.get("environment_name")
        or ""
    ).strip()
    if not environment or not status:
        return None

    plugin_updates = truthy_count(row.get("plugin_updates", "") or row.get("Plugin Updates", ""))
    theme_updates = truthy_count(row.get("theme_updates", "") or row.get("Theme Updates", ""))

    update_plugins = status in PLUGIN_STATUSES or plugin_updates > 0
    update_themes = theme_updates > 0
    update_wordpress = status in WORDPRESS_STATUSES
    if not (update_plugins or update_themes or update_wordpress):
        return None

    reason_parts: list[str] = []
    if status:
        reason_parts.append(status)
    if plugin_updates:
        reason_parts.append(f"{plugin_updates} plugin update(s)")
    if theme_updates:
        reason_parts.append(f"{theme_updates} theme update(s)")

    return UpdateQueueItem(
        account=account,
        site=site,
        environment=environment,
        status=status,
        update_plugins=update_plugins,
        update_themes=update_themes,
        update_wordpress=update_wordpress,
        requires_review=status == "Critical Update Needed",
        reason="; ".join(reason_parts),
    )


def load_queue(path: Path) -> list[UpdateQueueItem]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise RuntimeError(f"Queue input has no header row: {path}")
        queue = [item for row in reader if (item := build_queue_item(row))]
    return sorted(
        queue,
        key=lambda item: (
            item.requires_review is False,
            STATUS_PRIORITY.get(item.status, 99),
            item.account,
            item.site.lower(),
            item.environment.lower(),
        ),
    )


def write_queue(path: Path, queue: list[UpdateQueueItem]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "account",
                "site",
                "environment",
                "status",
                "update_plugins",
                "update_themes",
                "update_wordpress",
                "requires_review",
                "reason",
            ],
        )
        writer.writeheader()
        for item in queue:
            writer.writerow(
                {
                    "account": item.account,
                    "site": item.site,
                    "environment": item.environment,
                    "status": item.status,
                    "update_plugins": str(item.update_plugins).lower(),
                    "update_themes": str(item.update_themes).lower(),
                    "update_wordpress": str(item.update_wordpress).lower(),
                    "requires_review": str(item.requires_review).lower(),
                    "reason": item.reason,
                }
            )


def print_summary(queue: list[UpdateQueueItem]) -> None:
    print(f"Queued environments: {len(queue)}")
    print(f"Critical review required: {sum(1 for item in queue if item.requires_review)}")
    print(f"Plugin updates: {sum(1 for item in queue if item.update_plugins)}")
    print(f"Theme updates: {sum(1 for item in queue if item.update_themes)}")
    print(f"WordPress updates: {sum(1 for item in queue if item.update_wordpress)}")
    for item in queue[:10]:
        print(f"- {item.account} / {item.environment}: {item.reason}")
    if len(queue) > 10:
        print(f"... {len(queue) - 10} more")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--statuses-csv", default="portal-update-statuses.csv", type=Path)
    parser.add_argument("--out", default="update-queue.csv", type=Path)
    args = parser.parse_args()

    queue = load_queue(args.statuses_csv)
    write_queue(args.out, queue)
    print_summary(queue)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
