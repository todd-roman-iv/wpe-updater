# Phase 2: Plugin and Theme Update Automation

Phase 2 should stay guarded because it changes live WordPress environments.

## Workflow

1. Refresh `portal-update-statuses.csv` from the WP Engine portal.
2. Build an explicit queue:

```bash
python wpe_update_queue.py --statuses-csv portal-update-statuses.csv --out update-queue.csv
```

3. Review `update-queue.csv`.
4. Run preflight checks:

```bash
python wpe_update_preflight.py --queue update-queue.csv --config config.yml --out update-preflight.csv
```

5. Run updates only for rows with `preflight_passed=true`.

Dry-run the runner:

```bash
python wpe_update_runner.py --preflight update-preflight.csv --account sociusdms2
```

Apply mode is intentionally scoped:

```bash
python wpe_update_runner.py --preflight update-preflight.csv --account sociusdms2 --apply
```

Critical rows are skipped unless explicitly included:

```bash
python wpe_update_runner.py --preflight update-preflight.csv --account sociusdms2 --include-critical --apply
```

## Queue Rules

- `Critical Update Needed` queues plugin updates and marks `requires_review=true`.
- `Plugins Outdated` queues plugin updates.
- `WP Outdated` queues a WordPress/core update placeholder.
- Theme updates are queued when the input has a `theme_updates` or `Theme Updates` count.

## Runner Design

The next runner should use the WP Engine portal rather than the public Hosting API,
because the available update controls live in the User Portal / Smart Plugin
Manager UI.

Proposed safeguards:

- dry-run is the default.
- `--apply` is required before clicking update controls.
- `--environment ENV` or `--account ACCOUNT` limits scope.
- Critical rows require `--include-critical`.
- The runner writes an update log CSV after every attempted environment.
- The runner should update one environment at a time and wait for the portal's
preview/update confirmation state before moving on.
- Once an environment has no plugin/theme update controls remaining, emit
  `Update Complete` for that environment and apply it to the sheet.

## Preflight Rules

- A completed backup must exist within the configured backup window. The default
  is `36` hours, covering a backup roughly one day prior to update time.
- PHP versions below `8.1` produce a compatibility warning.
- If plugin inventory shows both `NextGEN Gallery` and `NextGEN Gallery Pro`, the
  environment is blocked and should be marked `Plugin Update Error`.

Apply preflight status overrides to the sheet:

```bash
python wpe_updates_sync.py --config config.yml --updates-csv update-preflight.csv --status-only
```

Apply completed update statuses to the sheet:

```bash
python wpe_updates_sync.py --config config.yml --updates-csv update-complete-statuses.csv --status-only
```

## Notes

WP Engine's Smart Plugin Manager supports plugin and theme updates with visual
regression testing and rollback behavior. Manual portal updates should still be
treated as production-impacting operations.
