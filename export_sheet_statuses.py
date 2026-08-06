from __future__ import annotations

import csv
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build


BASE = Path(__file__).resolve().parent
SPREADSHEET_ID = "1EzOfYHiQUp8T7JJn0LGz8Fiw9i5Rv7HOM8s6orDKCnc"
SHEET_RANGE = "'WPE Updates Q3 2026'!A3:O300"
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
        .get(spreadsheetId=SPREADSHEET_ID, range=SHEET_RANGE)
        .execute()
        .get("values", [])
    )

    out_path = BASE / "sheet-current-statuses.csv"
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["account", "row", "site", "environment", "status", "php"],
        )
        writer.writeheader()
        for row_number, row in enumerate(values, start=3):
            for account, start in ACCOUNT_STARTS.items():
                site = row[start + 1] if len(row) > start + 1 else ""
                environment = row[start + 2] if len(row) > start + 2 else ""
                status = row[start + 3] if len(row) > start + 3 else ""
                php = row[start + 4] if len(row) > start + 4 else ""
                if environment:
                    writer.writerow(
                        {
                            "account": account,
                            "row": row_number,
                            "site": site,
                            "environment": environment,
                            "status": status,
                            "php": php,
                        }
                    )
    print(out_path)


if __name__ == "__main__":
    main()
