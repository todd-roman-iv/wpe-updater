# GitHub + Apps Script Setup

This hybrid setup uses Google Apps Script as the sheet control panel and GitHub
Actions as the Python runtime.

## 1. Push This Folder To GitHub

Push the contents of `outputs/wpe-updates-tool` to a GitHub repo. Keep the repo
private unless you intentionally want the spreadsheet ID and automation code
public.

Do not commit these local files:

- `google-service-account.json`
- `config.yml`
- `.venv/`
- generated `*.csv` files

They are ignored by `.gitignore`.

## 2. Add GitHub Secrets

In GitHub, open the repo, then go to:

`Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`

Add:

- `GOOGLE_SERVICE_ACCOUNT_JSON`: the full contents of `google-service-account.json`
- `WPE_API_BASIC`: base64 WP Engine API credentials

Or, instead of `WPE_API_BASIC`, add both:

- `WPE_API_USER`
- `WPE_API_PASSWORD`

## 3. Test GitHub Actions Manually

Open:

`Actions` -> `WP Engine Sheet Automation` -> `Run workflow`

Good first tests:

- `scan_dns`, account `sociusdms3`, environment `spartanewr`
- `refresh_environments`
- `prepare_updates`

The workflow writes directly to the Google Sheet using the service account.

## 4. Add Apps Script To The Google Sheet

In the Google Sheet, open:

`Extensions` -> `Apps Script`

Add the contents of:

- `apps-script/Code.gs`
- `apps-script/appsscript.json`

## 5. Set Apps Script Properties

In Apps Script, open:

`Project Settings` -> `Script Properties`

Add:

- `GITHUB_OWNER`: your GitHub username or org
- `GITHUB_REPO`: the repo name
- `GITHUB_TOKEN`: a GitHub fine-grained token that can dispatch workflows
- `GITHUB_REF`: `main`
- `GITHUB_WORKFLOW_FILE`: `wpengine-sheet.yml`

The token needs permission to run Actions workflows for this repo.

## 6. Use The Sheet Menu

Reload the spreadsheet. A `WP Engine Updates` menu appears with:

- `Refresh environments + PHP`
- `Scan DNS Elsewhere - all accounts`
- `Scan DNS Elsewhere - selected row`
- `Prepare update queue + preflight`
- `Dry-run update batch`

The current GitHub runner prepares and verifies update batches. The final
headless plugin/theme update runner still needs the implementation that actually
clicks or calls WP Engine update actions.
