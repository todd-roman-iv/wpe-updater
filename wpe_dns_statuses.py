#!/usr/bin/env python3
"""Find WP Engine environments whose domains are not pointed/active."""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path
from typing import Any

from wpe_updates_sync import (
    fetch_all,
    find_accounts,
    load_config,
    normalize_key,
    wpe_auth_header,
)


DNS_ELSEWHERE_STATUS = "DNS Elsewhere"
OK_DNS_STATUSES = {"active", "pointed", "enabled", "ok"}
ERROR_DNS_MARKERS = {
    "aaaarecorddetected",
    "error",
    "failed",
    "failure",
    "inactive",
    "misconfigured",
    "notactive",
    "notpointed",
    "notverified",
    "pending",
    "unverified",
}


def nested_value(data: dict[str, Any], keys: list[str]) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def normalize_status(value: Any) -> str:
    return normalize_key(str(value or ""))


def domain_dns_status_values(domain: dict[str, Any]) -> list[tuple[str, str]]:
    candidates = [
        ("network_status", nested_value(domain, ["network_details", "network_info", "status"])),
        ("dns_status", nested_value(domain, ["network_details", "dns_info", "status"])),
        ("dns_status", nested_value(domain, ["dns", "status"])),
        ("status_message", nested_value(domain, ["network_details", "network_info", "message"])),
        ("status_message", nested_value(domain, ["network_details", "dns_info", "message"])),
        ("dns_status", domain.get("dns_status")),
        ("domain_status", domain.get("status")),
        ("status_message", domain.get("status_message")),
        ("status_message", domain.get("message")),
    ]
    return [
        (label, str(value).strip())
        for label, value in candidates
        if value is not None and str(value).strip()
    ]


def is_dns_error_domain(domain: dict[str, Any]) -> bool:
    status_values = domain_dns_status_values(domain)
    for _, value in status_values:
        normalized = normalize_status(value)
        if normalized in OK_DNS_STATUSES:
            continue
        if any(marker in normalized for marker in ERROR_DNS_MARKERS):
            return True

    if not status_values and normalize_status(domain.get("ownership_status")) == "txtverificationpending":
        return True

    return False


def describe_dns_issue(domain: dict[str, Any]) -> str:
    status_values = domain_dns_status_values(domain)
    if status_values:
        return "; ".join(f"{label}={value}" for label, value in status_values)
    ownership_status = str(domain.get("ownership_status") or "").strip()
    if ownership_status:
        return f"ownership_status={ownership_status}"
    return "DNS status unavailable"


def detect_dns_elsewhere_rows(
    config_path: Path,
    account_filter: set[str] | None = None,
    environment_filter: set[str] | None = None,
) -> list[dict[str, str]]:
    config = load_config(config_path)
    headers = wpe_auth_header()
    accounts = find_accounts(config.accounts, fetch_all("/accounts", headers))
    rows: list[dict[str, str]] = []

    for account_config in config.accounts:
        if account_filter and account_config.name not in account_filter:
            continue

        account = accounts[account_config.name]
        sites = fetch_all("/sites", headers, account_id=account["id"])
        for site in sorted(sites, key=lambda item: item.get("name", "").lower()):
            for install in sorted(site.get("installs", []), key=lambda item: item.get("name", "")):
                install_id = install.get("id")
                environment = str(install.get("name", "")).strip()
                if not install_id or not environment:
                    continue
                if environment_filter and normalize_key(environment) not in environment_filter:
                    continue

                domains = fetch_all(f"/installs/{install_id}/domains", headers)
                error_domains = [domain for domain in domains if is_dns_error_domain(domain)]
                if not error_domains:
                    continue

                rows.append(
                    {
                        "account": account_config.name,
                        "site": str(site.get("name", "")),
                        "environment": environment,
                        "status": DNS_ELSEWHERE_STATUS,
                        "domain": str(error_domains[0].get("name", "")),
                        "dns_status": describe_dns_issue(error_domains[0]),
                    }
                )

    return rows


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["account", "site", "environment", "status", "domain", "dns_status"],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yml", type=Path)
    parser.add_argument(
        "--out",
        default=Path(f"dns-elsewhere-statuses-{date.today().isoformat()}.csv"),
        type=Path,
    )
    parser.add_argument(
        "--account",
        action="append",
        help="Limit detection to one account. Can be passed multiple times.",
    )
    parser.add_argument(
        "--environment",
        action="append",
        help="Limit detection to one environment/install name. Can be passed multiple times.",
    )
    args = parser.parse_args()

    environment_filter = {normalize_key(item) for item in args.environment or []} or None
    rows = detect_dns_elsewhere_rows(
        args.config,
        set(args.account or []) or None,
        environment_filter,
    )
    write_rows(args.out, rows)
    print(f"Wrote {len(rows)} DNS Elsewhere status rows to {args.out}")
    for row in rows[:20]:
        print(
            f"- {row['account']}: {row['site']} / {row['environment']} "
            f"({row['domain']}: {row['dns_status']})"
        )
    if len(rows) > 20:
        print(f"  ... {len(rows) - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
