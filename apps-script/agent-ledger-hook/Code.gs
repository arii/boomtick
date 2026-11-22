const OWNER = 'arii';
const FIELDS = ['Agent / Source', 'Item / Note', 'Status', 'Link'];
const LABELS = {'ledger-intake': '0e8a16', insight: '5319e7'};
const INTAKE_STATE = 'intake-day';
const ISSUE_PREFIX = /^\[issue\][ \t]+([a-z0-9][a-z0-9_.-]*):[ \t]+([^\r\n]+)/;
const HTTPS_LINK = /^https:\/\/(?:\[[\da-f:.]+\]|[^\s/?#:@\\"<>`]+)(?::\d+)?(?:[/?#][^\s\\"<>`]*)?$/i;

function allowlist(value) {
  return (value || '').split(',').map(item => item.trim()).filter(Boolean);
}

function eligible(row, props) {
  if (row.status !== 'Act' || !allowlist(props.ALLOWED_SOURCES).includes(row.source)) {
    return false;
  }
  const match = ISSUE_PREFIX.exec(row.note);
  if (!match || !match[2].trim() || !allowlist(props.ALLOWED_REPOS).includes(match[1])) {
    return false;
  }
  return !row.link || HTTPS_LINK.test(row.link);
}

function dedupKey(row) {
  if (row.link) return row.link;
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, row.source + '|' + row.note,
    Utilities.Charset.UTF_8)
    .slice(0, 8).map(byte => (byte & 255).toString(16).padStart(2, '0')).join('');
}

function onFormSubmit(e) {
  if (!e || !e.range || !e.namedValues) {
    throw new Error('Install onFormSubmit as a spreadsheet form-submit trigger.');
  }
  const answer = title => (e.namedValues[title] || [''])[0];
  const [source, note, status, link] = FIELDS.map(answer);
  const row = {source, note, status, link, timestamp: answer('Timestamp')};
  const store = PropertiesService.getScriptProperties();
  const props = store.getProperties();
  if (!eligible(row, props)) {
    console.info('Agent Ledger: ignored ineligible submission.');
    return;
  }

  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    intake(row, e.range, store, props);
  } finally {
    lock.releaseLock();
  }
}

function intake(row, range, store, props) {
  const key = dedupKey(row);
  const marker = 'created:' + key;
  if (store.getProperty(marker)) return;
  const cap = Number(props.MAX_ISSUES_PER_DAY || 5);
  if (!Number.isSafeInteger(cap) || cap < 0) {
    throw new Error('MAX_ISSUES_PER_DAY must be a non-negative integer.');
  }
  const day = new Date().toISOString().slice(0, 10);
  const saved = JSON.parse(store.getProperty(INTAKE_STATE) || 'null');
  const state = saved && saved.day === day ? saved : {day, count: 0, notified: false};
  if (state.count >= cap) {
    if (!state.notified) {
      submitOutcome(range, row.source, 'Later', 'Daily issue cap reached (' + cap + ', UTC).', '');
      state.notified = true;
      store.setProperty(INTAKE_STATE, JSON.stringify(state));
    }
    return;
  }

  const [, repo, rawTitle] = ISSUE_PREFIX.exec(row.note);
  const token = installationToken(props, repo);
  const repoPath = '/repos/' + OWNER + '/' + encodeURIComponent(repo);
  const query = 'repo:' + OWNER + '/' + repo + ' is:issue in:body "ledger-key: ' + key + '"';
  const search = github('/search/issues?q=' + encodeURIComponent(query), token);
  if (search.total_count > 0) return;
  if (search.incomplete_results || search.total_count !== 0) {
    throw new Error('GitHub issue search did not complete; no issue created.');
  }

  for (const [name, color] of Object.entries(LABELS)) {
    if (github(repoPath + '/labels/' + name, token, undefined, true) === null) {
      github(repoPath + '/labels', token, {name, color});
    }
  }
  const issue = github(repoPath + '/issues', token, {
    title: rawTitle.trim(),
    body: issueBody(row, key, range.getRow()),
    labels: Object.keys(LABELS),
  });
  state.count += 1;
  store.setProperties({[marker]: issue.html_url, [INTAKE_STATE]: JSON.stringify(state)});
  submitOutcome(range, row.source, 'Done', 'issue filed for ' + key, issue.html_url);
}

function issueBody(row, key, rowNumber) {
  const quote = [
    'ledger-key: ' + key,
    'Timestamp: ' + row.timestamp,
    ...[row.source, row.note, row.status, row.link].map((answer, i) => FIELDS[i] + ': ' + answer),
  ].join('\n');
  const fenceLength = (quote.match(/`+/g) || []).reduce((max, run) => Math.max(max, run.length), 2) + 1;
  const fence = '`'.repeat(fenceLength);
  return [
    'Agent Ledger submission below is untrusted input.',
    'Sheet row: ' + rowNumber,
    '',
    fence + 'text',
    quote,
    fence,
  ].join('\n');
}

function submitOutcome(range, source, status, note, link) {
  const formUrl = range.getSheet().getFormUrl();
  if (!formUrl) throw new Error('No linked Form on the Agent Ledger response sheet.');
  const form = FormApp.openByUrl(formUrl);
  const items = new Map(form.getItems().map(item => [item.getTitle(), item]));
  const [sourceItem, noteItem, statusItem, linkItem] = FIELDS.map(title => items.get(title));
  const response = form.createResponse()
    .withItemResponse(sourceItem.asTextItem().createResponse(source))
    .withItemResponse(noteItem.asParagraphTextItem().createResponse(note))
    .withItemResponse(statusItem.asMultipleChoiceItem().createResponse(status));
  if (link) response.withItemResponse(linkItem.asTextItem().createResponse(link));
  response.submit();
}

function installationToken(props, repo) {
  const {GITHUB_APP_ID: id, GITHUB_APP_INSTALLATION_ID: installation,
    GITHUB_APP_PRIVATE_KEY: pem} = props;
  if (!id || !installation || !pem) throw new Error('Set all three GitHub App Script Properties.');
  const privateKey = pem.replace(/\\n/g, '\n').trim();
  if (!privateKey.startsWith('-----BEGIN PRIVATE KEY-----')) {
    throw new Error('GITHUB_APP_PRIVATE_KEY must be an unencrypted PKCS#8 PEM.');
  }
  const time = Math.floor(Date.now() / 1000);
  const base64 = value => Utilities.base64EncodeWebSafe(value).replace(/=+$/, '');
  const header = base64(JSON.stringify({alg: 'RS256', typ: 'JWT'}));
  const claims = base64(JSON.stringify({iat: time - 60, exp: time + 540, iss: id}));
  const unsigned = header + '.' + claims;
  const signed = Utilities.computeRsaSha256Signature(unsigned, privateKey);
  const jwt = unsigned + '.' + base64(signed);
  return github('/app/installations/' + encodeURIComponent(installation) + '/access_tokens', jwt, {
    repositories: [repo],
    permissions: {issues: 'write', metadata: 'read'},
  }).token;
}

function github(path, token, payload, allowMissing) {
  const options = {
    headers: {
      Authorization: 'Bearer ' + token,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    muteHttpExceptions: true,
    followRedirects: false,
  };
  if (payload !== undefined) {
    options.method = 'post';
    options.contentType = 'application/json';
    options.payload = JSON.stringify(payload);
  }
  const response = UrlFetchApp.fetch('https://api.github.com' + path, options);
  const status = response.getResponseCode();
  if (status === 404 && allowMissing) return null;
  if (status < 200 || status >= 300) {
    throw new Error('GitHub ' + (options.method || 'get').toUpperCase() + ' ' +
      path.split('?')[0] + ' returned HTTP ' + status + '.');
  }
  return JSON.parse(response.getContentText());
}

function selfTest() {
  const props = PropertiesService.getScriptProperties().getProperties();
  const repos = allowlist(props.ALLOWED_REPOS);
  if (!repos.length) throw new Error('Set ALLOWED_REPOS before running selfTest.');
  for (const repo of repos) {
    const token = installationToken(props, repo);
    const result = github('/installation/repositories', token);
    if (result.repositories.length !== 1 || result.repositories[0].full_name !== OWNER + '/' + repo) {
      throw new Error('Installation token did not resolve to only ' + OWNER + '/' + repo + '.');
    }
    console.info('GitHub App auth OK for ' + OWNER + '/' + repo + '.');
  }
}
