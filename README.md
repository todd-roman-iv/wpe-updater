# WP Engine Quarterly Updates Sheet Tool

This tool fills the `WPE Updates Q3 2026` tab from WP Engine account/site data.

It can run locally from VS Code/Terminal or as a hybrid Google Sheets + GitHub
Actions automation. For the Apps Script control panel and GitHub setup, see
`docs/github-apps-script-setup.md`.

It uses the WP Engine Hosting API to:

- list accessible accounts,
- match `sociusdms`, `sociusdms2`, and `sociusdms3`,
- list sites for each matched account,
- write one environment/install per row into each account's 5-column block.

These sheet fields are populated:

- counter column: `1`
- site name
- environment name
- status: preserved when possible, or blanked with `--reset-status`
- PHP version

PHP cells are color-coded:

- `7.4`: light red 2
- `8.2`: light yellow 2

## Setup

Create a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy the example config:

```bash
cp config.example.yml config.yml
```

Create WP Engine API credentials in the WP Engine portal, then set either:

```bash
export WPE_API_USER="your-wpe-api-user"
export WPE_API_PASSWORD="your-wpe-api-password"
```

or:

```bash
export WPE_API_BASIC="base64-user-colon-password"
```

Create a Google Cloud service account with Google Sheets API access, download the JSON key, and share the spreadsheet with the service account email. Then set:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/absolute/path/to/service-account.json"
```

## Preview

```bash
python wpe_updates_sync.py --config config.yml --dry-run
```

## Export CSV

```bash
python wpe_updates_sync.py --config config.yml --dry-run --csv wpe-environments.csv
```

## Update the Google Sheet

Preserve any matching existing status values:

```bash
python wpe_updates_sync.py --config config.yml
```

Populate Status from WP Engine's `Needs Updates` export:

```bash
python wpe_updates_sync.py --config config.yml --updates-csv /absolute/path/to/wpengine-needs-updates.csv
```

Only update existing Status cells from a portal scrape/status CSV:

```bash
python wpe_updates_sync.py --config config.yml --updates-csv portal-update-statuses.csv --status-only
```

The status priority is:

- critical/vulnerable plugin indicator: `Critical Update Needed`
- WordPress/core update indicator: `WP Outdated`
- 5 or more plugin updates: `Plugins Outdated`

Find environments where WP Engine reports a domain DNS issue, then mark those
rows `DNS Elsewhere`:

```bash
python wpe_dns_statuses.py --config config.yml --out dns-elsewhere-statuses-2026-08-06.csv
python wpe_updates_sync.py --config config.yml --updates-csv dns-elsewhere-statuses-2026-08-06.csv --status-only
```

Start fresh and blank the status columns:

```bash
python wpe_updates_sync.py --config config.yml --reset-status
```

## Sheet Layout

The default config writes these account blocks:

- `A:E` for `sociusdms`
- `F:J` for `sociusdms2`
- `K:O` for `sociusdms3`

Rows `1` and `2` are headers. Data rows are `3:300`, matching the quarterly sheet pattern.

## Phase 2 Queue

Build a reviewed plugin/theme update queue from the current status CSV:

```bash
python wpe_update_queue.py --statuses-csv portal-update-statuses.csv --out update-queue.csv
```

Review `update-queue.csv` before running any update automation.

Run preflight checks before any update automation:

```bash
python wpe_update_preflight.py --queue update-queue.csv --config config.yml --out update-preflight.csv
```

Dry-run the guarded update runner:

```bash
python wpe_update_runner.py --preflight update-preflight.csv --account sociusdms2
```
