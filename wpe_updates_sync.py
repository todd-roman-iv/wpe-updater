#!/usr/bin/env python3
"""Populate a WP Engine quarterly update Google Sheet."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


WPE_API_BASE = "https://api.wpengineapi.com/v1"
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
ACCOUNT_BLOCK_WIDTH = 5
PHP_BACKGROUND_COLORS = {
    "7.4": {"red": 0.91764706, "green": 0.6, "blue": 0.6},
    "8.2": {"red": 1.0, "green": 0.8509804, "blue": 0.4},
}
AUTO_STATUSES = {
    "Critical Update Needed",
    "DNS Elsewhere",
    "WP Outdated",
    "Plugins Outdated",
    "Plugin Update Error",
    "Update Complete",
}
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}


@dataclass(frozen=True)
class AccountConfig:
    name: str
    start_column: str


@dataclass(frozen=True)
class SheetConfig:
    spreadsheet_id: str
    worksheet_name: str
    first_data_row: int
    last_data_row: int
    accounts: list[AccountConfig]
    write_headers: bool
    preserve_status: bool


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def load_config(path: Path) -> SheetConfig:
    import yaml

    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    return SheetConfig(
        spreadsheet_id=raw["spreadsheet_id"],
        worksheet_name=raw["worksheet_name"],
        first_data_row=int(raw.get("first_data_row", 3)),
        last_data_row=int(raw.get("last_data_row", 300)),
        accounts=[
            AccountConfig(name=item["name"], start_column=item["start_column"])
            for item in raw["accounts"]
        ],
        write_headers=bool(raw.get("write_headers", True)),
        preserve_status=bool(raw.get("preserve_status", True)),
    )


def column_to_index(column: str) -> int:
    result = 0
    for char in column.upper():
        if not "A" <= char <= "Z":
            raise ValueError(f"Invalid column: {column}")
        result = result * 26 + (ord(char) - ord("A") + 1)
    return result


def index_to_column(index: int) -> str:
    if index < 1:
        raise ValueError("Column index must be positive")
    chars: list[str] = []
    while index:
        index, remainder = divmod(index - 1, 26)
        chars.append(chr(ord("A") + remainder))
    return "".join(reversed(chars))


def wpe_auth_header() -> dict[str, str]:
    credentials = os.environ.get("WPE_API_BASIC")
    if not credentials:
        user = os.environ.get("WPE_API_USER")
        password = os.environ.get("WPE_API_PASSWORD")
        if not user or not password:
            raise RuntimeError(
                "Set WPE_API_BASIC or both WPE_API_USER and WPE_API_PASSWORD."
            )
        credentials = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {credentials}"}


def fetch_page(endpoint: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{WPE_API_BASE}{endpoint}?{query}",
        headers=headers,
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"WP Engine API error {exc.code}: {body}") from exc


def fetch_all(endpoint: str, headers: dict[str, str], **params: Any) -> list[dict[str, Any]]:
    limit = 100
    offset = 0
    results: list[dict[str, Any]] = []
    while True:
        page = fetch_page(endpoint, {"limit": limit, "offset": offset, **params}, headers)
        batch = page.get("results", [])
        results.extend(batch)
        if not page.get("next") or not batch:
            break
        offset += limit
    return results


def find_accounts(
    account_configs: list[AccountConfig],
    wpe_accounts: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for account in wpe_accounts:
        for key in (account.get("name"), account.get("nickname")):
            if key:
                by_name[key.lower()] = account

    found: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for account_config in account_configs:
        account = by_name.get(account_config.name.lower())
        if account:
            found[account_config.name] = account
        else:
            missing.append(account_config.name)

    if missing:
        available = ", ".join(sorted({a.get("name", "") for a in wpe_accounts if a.get("name")}))
        raise RuntimeError(
            f"Could not find WP Engine account(s): {', '.join(missing)}. "
            f"Available account names: {available or '(none)'}"
        )
    return found


def fetch_site_rows(config: SheetConfig) -> dict[str, list[dict[str, str]]]:
    headers = wpe_auth_header()
    accounts = find_accounts(config.accounts, fetch_all("/accounts", headers))
    rows_by_account: dict[str, list[dict[str, str]]] = {}

    for account_config in config.accounts:
        account = accounts[account_config.name]
        sites = fetch_all("/sites", headers, account_id=account["id"])
        site_rows: list[dict[str, str]] = []
        for site in sorted(sites, key=lambda item: item.get("name", "").lower()):
            installs = sorted(
                site.get("installs", []),
                key=lambda item: (item.get("environment", ""), item.get("name", "")),
            )
            for install in installs:
                site_rows.append(
                    {
                        "site_name": str(site.get("name", "")),
                        "environment_name": str(install.get("name", "")),
                        "environment_type": str(install.get("environment", "")),
                        "php_version": str(install.get("php_version", "")),
                    }
                )
        rows_by_account[account_config.name] = site_rows

    return rows_by_account


def first_matching_value(row: dict[str, str], patterns: list[str]) -> str:
    normalized_patterns = [normalize_key(pattern) for pattern in patterns]
    for key, value in row.items():
        normalized_key = normalize_key(key)
        if any(pattern in normalized_key for pattern in normalized_patterns):
            return value.strip()
    return ""


def matching_values(row: dict[str, str], patterns: list[str]) -> list[str]:
    normalized_patterns = [normalize_key(pattern) for pattern in patterns]
    values: list[str] = []
    for key, value in row.items():
        normalized_key = normalize_key(key)
        if any(pattern in normalized_key for pattern in normalized_patterns):
            values.append(value.strip())
    return values


def contains_meaningful_update_value(value: str) -> bool:
    normalized = value.strip().lower()
    return bool(normalized) and normalized not in {"0", "0.0", "none", "n/a", "na", "no", "false"}


def extract_largest_int(values: list[str]) -> int:
    largest = 0
    for value in values:
        for match in re.findall(r"\d+", value):
            largest = max(largest, int(match))
    return largest


def status_from_update_row(row: dict[str, str]) -> str:
    all_text = " ".join(row.values()).lower()
    vulnerability_values = matching_values(row, ["vulnerability", "vulnerabilities", "critical"])
    plugin_values = matching_values(row, ["plugin"])

    if (
        "exclamation-shield" in all_text
        or "detected vulnerabilities" in all_text
        or "vulnerabilities with plugins" in all_text
        or extract_largest_int(vulnerability_values) > 0
    ):
        return "Critical Update Needed"
    for key, value in row.items():
        normalized_key = normalize_key(key)
        is_wordpress_key = (
            "wordpress" in normalized_key
            or "wpcore" in normalized_key
            or normalized_key in {"wp", "core"}
        )
        is_update_key = any(
            marker in normalized_key
            for marker in ("update", "outdated", "available", "latest", "new")
        )
        is_simple_portal_key = normalized_key in {"wordpress", "wp", "core", "wordpresscore"}
        if is_wordpress_key and (is_update_key or is_simple_portal_key) and contains_meaningful_update_value(value):
            return "WP Outdated"
    if extract_largest_int(plugin_values) >= 5:
        return "Plugins Outdated"
    return ""


def load_update_statuses(path: Path) -> dict[tuple[str, str], str]:
    statuses: dict[tuple[str, str], str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise RuntimeError(f"Updates CSV has no header row: {path}")
        for row in reader:
            clean_row = {key or "": value or "" for key, value in row.items()}
            supplied_status = first_matching_value(clean_row, ["statusoverride", "status_override"])
            if not supplied_status:
                supplied_status = first_matching_value(clean_row, ["status"])
            status = supplied_status if supplied_status in AUTO_STATUSES else status_from_update_row(clean_row)
            if not status:
                continue

            site = first_matching_value(clean_row, ["site", "sitename"])
            environment = first_matching_value(clean_row, ["environment", "install", "environmentname"])
            if not environment:
                continue
            statuses[(normalize_key(site), normalize_key(environment))] = status
            statuses[("", normalize_key(environment))] = status
    return statuses


def update_status_for_site(
    status_updates: dict[tuple[str, str], str],
    site_name: str,
    environment_name: str,
) -> str:
    site_key = normalize_key(site_name)
    environment_key = normalize_key(environment_name)
    return status_updates.get((site_key, environment_key), status_updates.get(("", environment_key), ""))


def build_sheet_values(
    config: SheetConfig,
    rows_by_account: dict[str, list[dict[str, str]]],
    existing_statuses: dict[str, dict[tuple[str, str], str]] | None = None,
    update_statuses: dict[tuple[str, str], str] | None = None,
    reset_status: bool = False,
) -> list[list[str | int]]:
    row_count = config.last_data_row - config.first_data_row + 1
    total_columns = max(column_to_index(account.start_column) + ACCOUNT_BLOCK_WIDTH - 1 for account in config.accounts)
    values: list[list[str | int]] = [["" for _ in range(total_columns)] for _ in range(row_count)]

    for account in config.accounts:
        start_idx = column_to_index(account.start_column) - 1
        statuses = existing_statuses.get(account.name, {}) if existing_statuses else {}
        for row_idx, site in enumerate(rows_by_account.get(account.name, [])[:row_count]):
            status = ""
            update_status = update_status_for_site(
                update_statuses or {},
                site["site_name"],
                site["environment_name"],
            )
            if update_status:
                status = update_status
            elif config.preserve_status and not reset_status:
                status = statuses.get((site["site_name"], site["environment_name"]), "")
            values[row_idx][start_idx : start_idx + ACCOUNT_BLOCK_WIDTH] = [
                1,
                site["site_name"],
                site["environment_name"],
                status,
                site["php_version"],
            ]
    return values


def build_header_values(config: SheetConfig) -> list[list[str]]:
    total_columns = max(column_to_index(account.start_column) + ACCOUNT_BLOCK_WIDTH - 1 for account in config.accounts)
    headers = [["" for _ in range(total_columns)] for _ in range(2)]
    for account in config.accounts:
        start_idx = column_to_index(account.start_column) - 1
        counter_col = account.start_column.upper()
        headers[0][start_idx] = f"=SUM({counter_col}{config.first_data_row}:{counter_col}{config.last_data_row})"
        headers[0][start_idx + 1] = account.name
        headers[1][start_idx : start_idx + ACCOUNT_BLOCK_WIDTH] = [
            "",
            "Site Name",
            "Environment Name",
            "Status",
            "PHP",
        ]
    return headers


def get_sheets_service() -> Any:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
        raise RuntimeError(
            "Set GOOGLE_APPLICATION_CREDENTIALS to a Google service account JSON file."
        )
    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=[SHEETS_SCOPE],
    )
    return build("sheets", "v4", credentials=credentials)


def get_sheet_id(config: SheetConfig, service: Any) -> int:
    result = (
        service.spreadsheets()
        .get(
            spreadsheetId=config.spreadsheet_id,
            fields="sheets(properties(sheetId,title))",
        )
        .execute()
    )
    for sheet in result.get("sheets", []):
        properties = sheet.get("properties", {})
        if properties.get("title") == config.worksheet_name:
            return int(properties["sheetId"])
    raise RuntimeError(f"Could not find Google Sheet tab: {config.worksheet_name}")


def read_existing_statuses(config: SheetConfig, service: Any) -> dict[str, dict[tuple[str, str], str]]:
    sheet_name = quote_sheet_name(config.worksheet_name)
    end_column = index_to_column(max(column_to_index(account.start_column) + ACCOUNT_BLOCK_WIDTH - 1 for account in config.accounts))
    data_range = f"{sheet_name}!A{config.first_data_row}:{end_column}{config.last_data_row}"
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=config.spreadsheet_id, range=data_range)
        .execute()
    )
    values = result.get("values", [])
    statuses: dict[str, dict[tuple[str, str], str]] = {}

    for account in config.accounts:
        start_idx = column_to_index(account.start_column) - 1
        account_statuses: dict[tuple[str, str], str] = {}
        for row in values:
            site = row[start_idx + 1] if len(row) > start_idx + 1 else ""
            env = row[start_idx + 2] if len(row) > start_idx + 2 else ""
            status = row[start_idx + 3] if len(row) > start_idx + 3 else ""
            if site and env and status:
                account_statuses[(site, env)] = status
        statuses[account.name] = account_statuses
    return statuses


def quote_sheet_name(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def build_background_request(
    sheet_id: int,
    start_row_index: int,
    end_row_index: int,
    start_column_index: int,
    end_column_index: int,
    color: dict[str, float],
) -> dict[str, Any]:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row_index,
                "endRowIndex": end_row_index,
                "startColumnIndex": start_column_index,
                "endColumnIndex": end_column_index,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": color,
                }
            },
            "fields": "userEnteredFormat.backgroundColor",
        }
    }


def build_php_format_requests(
    config: SheetConfig,
    rows_by_account: dict[str, list[dict[str, str]]],
    sheet_id: int,
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    row_count = config.last_data_row - config.first_data_row + 1
    start_row_index = config.first_data_row - 1
    end_row_index = config.last_data_row

    for account in config.accounts:
        php_col_index = column_to_index(account.start_column) - 1 + 4
        requests.append(
            build_background_request(
                sheet_id,
                start_row_index,
                end_row_index,
                php_col_index,
                php_col_index + 1,
                WHITE,
            )
        )

        for row_idx, site in enumerate(rows_by_account.get(account.name, [])[:row_count]):
            color = PHP_BACKGROUND_COLORS.get(site["php_version"])
            if not color:
                continue
            absolute_row_index = start_row_index + row_idx
            requests.append(
                build_background_request(
                    sheet_id,
                    absolute_row_index,
                    absolute_row_index + 1,
                    php_col_index,
                    php_col_index + 1,
                    color,
                )
            )

    return requests


def write_sheet(
    config: SheetConfig,
    rows_by_account: dict[str, list[dict[str, str]]],
    values: list[list[str | int]],
    update_statuses: dict[tuple[str, str], str] | None,
    reset_status: bool,
) -> None:
    service = get_sheets_service()
    if config.preserve_status and not reset_status:
        existing_statuses = read_existing_statuses(config, service)
        values = build_sheet_values(
            config,
            rows_by_account,
            existing_statuses,
            update_statuses,
            reset_status,
        )

    sheet_name = quote_sheet_name(config.worksheet_name)
    end_column = index_to_column(len(values[0]))
    data_range = f"{sheet_name}!A{config.first_data_row}:{end_column}{config.last_data_row}"

    requests_body: list[dict[str, Any]] = []
    if config.write_headers:
        header_values = build_header_values(config)
        header_range = f"{sheet_name}!A1:{end_column}2"
        requests_body.append(
            {
                "range": header_range,
                "values": header_values,
            }
        )

    requests_body.append(
        {
            "range": data_range,
            "values": values,
        }
    )

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=config.spreadsheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": requests_body},
    ).execute()

    sheet_id = get_sheet_id(config, service)
    format_requests = build_php_format_requests(config, rows_by_account, sheet_id)
    if format_requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=config.spreadsheet_id,
            body={"requests": format_requests},
        ).execute()


def build_status_only_updates(
    config: SheetConfig,
    values: list[list[str]],
    update_statuses: dict[tuple[str, str], str],
    clear_missing_auto_statuses: bool = False,
) -> list[dict[str, Any]]:
    sheet_name = quote_sheet_name(config.worksheet_name)
    updates: list[dict[str, Any]] = []

    for row_idx, row in enumerate(values, start=config.first_data_row):
        for account in config.accounts:
            start_idx = column_to_index(account.start_column) - 1
            site = row[start_idx + 1] if len(row) > start_idx + 1 else ""
            environment = row[start_idx + 2] if len(row) > start_idx + 2 else ""
            if not environment:
                continue
            status = update_status_for_site(update_statuses, site, environment)
            if not status and not clear_missing_auto_statuses:
                continue
            existing_status = row[start_idx + 3] if len(row) > start_idx + 3 else ""
            if not status and existing_status not in AUTO_STATUSES:
                continue
            next_status = status if status else ""
            status_column = index_to_column(start_idx + 4)
            updates.append(
                {
                    "range": f"{sheet_name}!{status_column}{row_idx}",
                    "values": [[next_status]],
                }
            )
    return updates


def write_status_only(
    config: SheetConfig,
    update_statuses: dict[tuple[str, str], str],
    clear_missing_auto_statuses: bool = False,
) -> None:
    service = get_sheets_service()
    sheet_name = quote_sheet_name(config.worksheet_name)
    end_column = index_to_column(max(column_to_index(account.start_column) + ACCOUNT_BLOCK_WIDTH - 1 for account in config.accounts))
    data_range = f"{sheet_name}!A{config.first_data_row}:{end_column}{config.last_data_row}"
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=config.spreadsheet_id, range=data_range)
        .execute()
    )
    values = result.get("values", [])
    updates = build_status_only_updates(
        config,
        values,
        update_statuses,
        clear_missing_auto_statuses,
    )

    if not updates:
        print("No matching status updates found for existing sheet rows.")
        return

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=config.spreadsheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": updates},
    ).execute()
    print(f"Updated {len(updates)} status cells.")


def export_csv(path: Path, rows_by_account: dict[str, list[dict[str, str]]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "account",
                "site_name",
                "environment_name",
                "environment_type",
                "php_version",
            ],
        )
        writer.writeheader()
        for account, rows in rows_by_account.items():
            for row in rows:
                writer.writerow({"account": account, **row})


def print_summary(rows_by_account: dict[str, list[dict[str, str]]]) -> None:
    for account, rows in rows_by_account.items():
        print(f"{account}: {len(rows)} environments")
        for row in rows[:5]:
            print(f"  - {row['site_name']} / {row['environment_name']}")
        if len(rows) > 5:
            print(f"  ... {len(rows) - 5} more")


def warn_if_rows_exceed_sheet(config: SheetConfig, rows_by_account: dict[str, list[dict[str, str]]]) -> None:
    row_count = config.last_data_row - config.first_data_row + 1
    for account, rows in rows_by_account.items():
        if len(rows) > row_count:
            print(
                f"Warning: {account} has {len(rows)} environments, but the configured "
                f"sheet range only has {row_count} rows. Extra environments will be skipped.",
                file=sys.stderr,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yml", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset-status", action="store_true")
    parser.add_argument("--csv", type=Path, help="Export fetched environments to CSV.")
    parser.add_argument(
        "--updates-csv",
        type=Path,
        help="CSV of available updates downloaded from WP Engine's Needs Updates tab.",
    )
    parser.add_argument(
        "--status-only",
        action="store_true",
        help="Only update Status cells from --updates-csv; do not fetch WP Engine site/PHP data.",
    )
    parser.add_argument(
        "--clear-missing-auto-statuses",
        action="store_true",
        help="With --status-only, clear existing auto-managed statuses that are missing from --updates-csv.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    update_statuses = load_update_statuses(args.updates_csv) if args.updates_csv else None
    if args.status_only:
        if not update_statuses:
            raise RuntimeError("--status-only requires --updates-csv.")
        write_status_only(config, update_statuses, args.clear_missing_auto_statuses)
        return 0

    rows_by_account = fetch_site_rows(config)

    if args.csv:
        export_csv(args.csv, rows_by_account)
        print(f"Wrote {args.csv}")

    print_summary(rows_by_account)
    warn_if_rows_exceed_sheet(config, rows_by_account)
    if args.dry_run:
        return 0

    values = build_sheet_values(
        config,
        rows_by_account,
        update_statuses=update_statuses,
        reset_status=args.reset_status,
    )
    write_sheet(
        config,
        rows_by_account,
        values,
        update_statuses=update_statuses,
        reset_status=args.reset_status,
    )
    print(f"Updated Google Sheet tab: {config.worksheet_name}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
