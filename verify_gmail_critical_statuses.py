from __future__ import annotations

import csv
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build


BASE = Path(__file__).resolve().parent
SPREADSHEET_ID = "1EzOfYHiQUp8T7JJn0LGz8Fiw9i5Rv7HOM8s6orDKCnc"
RANGE = "'WPE Updates Q3 2026'!A3:O300"
ACCOUNT_STARTS = {"sociusdms": 0, "sociusdms2": 5, "sociusdms3": 10}


def main() -> None:
    creds = service_account.Credentials.from_service_account_file(
        BASE / "google-service-account.json",
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=creds)
    values = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range=RANGE)
        .execute()
        .get("values", [])
    )

    found = {}
    for row_number, row in enumerate(values, start=3):
        for account, start in ACCOUNT_STARTS.items():
            site = row[start + 1] if len(row) > start + 1 else ""
            environment = row[start + 2] if len(row) > start + 2 else ""
            status = row[start + 3] if len(row) > start + 3 else ""
            if environment:
                found[(account, environment)] = (row_number, site, status)

    missing = []
    wrong = []
    total = 0
    with (BASE / "gmail-critical-statuses-2026-08-04.csv").open(newline="", encoding="utf-8-sig") as fh:
        for item in csv.DictReader(fh):
            total += 1
            key = (item["account"], item["environment"])
            sheet_row = found.get(key)
            if not sheet_row:
                missing.append(key)
            elif sheet_row[2] != "Critical Update Needed":
                wrong.append((key, sheet_row))

    print(f"csv_rows={total}")
    print(f"missing={len(missing)}")
    print(f"wrong={len(wrong)}")
    if missing:
        print(f"missing_sample={missing[:20]}")
    if wrong:
        print(f"wrong_sample={wrong[:20]}")


if __name__ == "__main__":
    main()
