# WP Engine Portal Status Scrape

The WP Engine Hosting API provides site/environment/PHP data, but the User Portal
`Needs updates` tab is the source for the plugin/core/security indicators.

Current browser-backed flow:

1. Open `https://my.wpengine.com/sites`.
2. Use the account switcher to select each account:
   - `sociusdms`
   - `sociusdms2`
   - `sociusdms3`
3. Open `Needs updates`.
4. Scrape each environment card:
   - `Critical Update Needed` when the card has `aria-label="exclamation-shield"` or accessibility text like `We have detected vulnerabilities with plugins on this site environment`.
   - `WP Outdated` when the card has a WordPress/WP update badge.
   - `Plugins Outdated` when the card has `Plugins N outdated` and `N >= 5`.
5. Save `portal-update-statuses.csv`.
6. Run:

```bash
python wpe_updates_sync.py --config config.yml --updates-csv portal-update-statuses.csv
```

The sync script accepts either raw WP Engine update export columns or a direct
`status` column with one of:

- `Critical Update Needed`
- `WP Outdated`
- `Plugins Outdated`
