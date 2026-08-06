const WPE_WORKFLOW_FILE = 'wpengine-sheet.yml';

const WPE_TASKS = {
  REFRESH: 'refresh_environments',
  SCAN_DNS: 'scan_dns',
  PREPARE_UPDATES: 'prepare_updates',
  DRY_RUN_UPDATES: 'dry_run_updates',
};

const WPE_ACCOUNT_BLOCKS = [
  { account: 'sociusdms', startColumn: 1 },
  { account: 'sociusdms2', startColumn: 6 },
  { account: 'sociusdms3', startColumn: 11 },
];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('WP Engine Updates')
    .addItem('Refresh environments + PHP', 'wpeRefreshEnvironments')
    .addSeparator()
    .addItem('Scan DNS Elsewhere - all accounts', 'wpeScanDnsAll')
    .addItem('Scan DNS Elsewhere - selected row', 'wpeScanDnsSelectedRow')
    .addSeparator()
    .addItem('Prepare update queue + preflight', 'wpePrepareUpdates')
    .addItem('Dry-run update batch', 'wpeDryRunUpdates')
    .addSeparator()
    .addItem('Show setup status', 'wpeShowSetupStatus')
    .addToUi();
}

function wpeRefreshEnvironments() {
  wpeDispatchWorkflow_(WPE_TASKS.REFRESH, {});
}

function wpeScanDnsAll() {
  wpeDispatchWorkflow_(WPE_TASKS.SCAN_DNS, {});
}

function wpeScanDnsSelectedRow() {
  const selected = wpeSelectedEnvironment_();
  wpeDispatchWorkflow_(WPE_TASKS.SCAN_DNS, {
    account: selected.account,
    environment: selected.environment,
  });
}

function wpePrepareUpdates() {
  wpeDispatchWorkflow_(WPE_TASKS.PREPARE_UPDATES, {
    max_backup_age_hours: '36',
  });
}

function wpeDryRunUpdates() {
  const ui = SpreadsheetApp.getUi();
  const account = wpePromptOptional_(ui, 'Account filter', 'Optional. Example: sociusdms3');
  const environment = wpePromptOptional_(ui, 'Environment filter', 'Optional. Example: spartanewr');
  const includeCritical = ui.alert(
    'Include critical rows?',
    'Include environments marked Critical Update Needed in this dry run?',
    ui.ButtonSet.YES_NO
  ) === ui.Button.YES;

  wpeDispatchWorkflow_(WPE_TASKS.DRY_RUN_UPDATES, {
    account: account,
    environment: environment,
    include_critical: String(includeCritical),
    max_backup_age_hours: '36',
  });
}

function wpeShowSetupStatus() {
  const props = PropertiesService.getScriptProperties();
  const owner = props.getProperty('GITHUB_OWNER') || '(missing)';
  const repo = props.getProperty('GITHUB_REPO') || '(missing)';
  const ref = props.getProperty('GITHUB_REF') || 'main';
  const token = props.getProperty('GITHUB_TOKEN') ? '(set)' : '(missing)';
  SpreadsheetApp.getUi().alert(
    'WP Engine automation setup',
    `GITHUB_OWNER: ${owner}\nGITHUB_REPO: ${repo}\nGITHUB_REF: ${ref}\nGITHUB_TOKEN: ${token}`,
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}

function wpeDispatchWorkflow_(task, inputs) {
  const props = PropertiesService.getScriptProperties();
  const owner = wpeRequiredProperty_(props, 'GITHUB_OWNER');
  const repo = wpeRequiredProperty_(props, 'GITHUB_REPO');
  const token = wpeRequiredProperty_(props, 'GITHUB_TOKEN');
  const ref = props.getProperty('GITHUB_REF') || 'main';
  const workflowFile = props.getProperty('GITHUB_WORKFLOW_FILE') || WPE_WORKFLOW_FILE;

  const payload = {
    ref: ref,
    inputs: {
      task: task,
      account: inputs.account || '',
      environment: inputs.environment || '',
      include_critical: inputs.include_critical || 'false',
      max_backup_age_hours: inputs.max_backup_age_hours || '36',
    },
  };

  const response = UrlFetchApp.fetch(
    `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflowFile}/dispatches`,
    {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true,
    }
  );

  const code = response.getResponseCode();
  if (code !== 204) {
    throw new Error(`GitHub workflow dispatch failed (${code}): ${response.getContentText()}`);
  }

  SpreadsheetApp.getUi().alert(
    'Workflow started',
    `Started ${task}.\n\nView it at:\nhttps://github.com/${owner}/${repo}/actions/workflows/${workflowFile}`,
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}

function wpeRequiredProperty_(props, key) {
  const value = props.getProperty(key);
  if (!value) {
    throw new Error(`Missing Apps Script property: ${key}`);
  }
  return value;
}

function wpeSelectedEnvironment_() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const range = sheet.getActiveRange();
  const row = range.getRow();
  if (row < 3) {
    throw new Error('Select a data row first.');
  }

  for (const block of WPE_ACCOUNT_BLOCKS) {
    const site = String(sheet.getRange(row, block.startColumn + 1).getValue() || '').trim();
    const environment = String(sheet.getRange(row, block.startColumn + 2).getValue() || '').trim();
    if (environment) {
      return {
        account: block.account,
        site: site,
        environment: environment,
      };
    }
  }

  throw new Error('Could not find an environment name on the selected row.');
}

function wpePromptOptional_(ui, title, message) {
  const response = ui.prompt(title, message, ui.ButtonSet.OK_CANCEL);
  if (response.getSelectedButton() !== ui.Button.OK) {
    throw new Error('Cancelled.');
  }
  return response.getResponseText().trim();
}
