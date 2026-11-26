const OWNER = 'arii';
const FIELDS = ['Agent / Source', 'Item / Note', 'Status', 'Link'];
const LABELS = {'ledger-intake': '0e8a16', insight: '5319e7'};
// One submission at a time: the check-and-create below runs under the script lock.
// A submission that can't get the lock in time is not filed and gets one Later reply.
const LOCK_WAIT_MS = 30000;
const ISSUE_PREFIX = /^\[issue\][ \t]+([a-z0-9][a-z0-9_.-]*):[ \t]+([^\r\n]+)/;
const HTTPS_LINK = /^https:\/\/(?:\[[\da-f:.]+\]|[^\s/?#:@\\"<>`]+)(?::\d+)?(?:[/?#][^\s\\"<>`]*)?$/i;
const TASK_KEY = /^task-[a-z0-9-]+$/i;
const SCAN_WATERMARK = 'LAST_SCANNED_ROW';
const INTAKE_COLUMNS = ['intake_id', 'dedupe_hash', 'missing_fields', 'status'];
// The one canonical list of required fields, in the order missing_fields reports them.
// Each maps to the note section it is parsed from, or to the [issue] prefix for title and repo.
const REQUIRED_FIELDS = ['title', 'repo', 'problem', 'scope', 'done_when'];
const FIELD_LABELS = {title: 'title', repo: 'repo', problem: 'Problem', scope: 'Out of scope', done_when: 'Done when'};
const HASH_MARKER = 'hash:';
// Python str.isspace() set, used for strip() and re \s in ledger_intake.normalize().
const PY_SPACE = '\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000';
const PY_SPACE_EDGES = new RegExp('^[' + PY_SPACE + ']+|[' + PY_SPACE + ']+$', 'g');
const PY_SPACE_RUNS = new RegExp('[' + PY_SPACE + ']+', 'g');
// Full case folds that differ from per-character toLowerCase(), as hex code points
// ("source=folded+folded"). Generated from Python str.casefold() vs str.lower() (Unicode 14).
const CASEFOLD_EXTRA = new Map((
  'b5=3bc df=73+73 149=2bc+6e 17f=73 1f0=6a+30c 345=3b9 390=3b9+308+301 3b0=3c5+308+301 3c2=3c3 ' +
  '3d0=3b2 3d1=3b8 3d5=3c6 3d6=3c0 3f0=3ba 3f1=3c1 3f5=3b5 587=565+582 1c80=432 1c81=434 1c82=43e ' +
  '1c83=441 1c84=442 1c85=442 1c86=44a 1c87=463 1c88=a64b 1e96=68+331 1e97=74+308 1e98=77+30a ' +
  '1e99=79+30a 1e9a=61+2be 1e9b=1e61 1e9e=73+73 1f50=3c5+313 1f52=3c5+313+300 1f54=3c5+313+301 ' +
  '1f56=3c5+313+342 1f80=1f00+3b9 1f81=1f01+3b9 1f82=1f02+3b9 1f83=1f03+3b9 1f84=1f04+3b9 ' +
  '1f85=1f05+3b9 1f86=1f06+3b9 1f87=1f07+3b9 1f88=1f00+3b9 1f89=1f01+3b9 1f8a=1f02+3b9 ' +
  '1f8b=1f03+3b9 1f8c=1f04+3b9 1f8d=1f05+3b9 1f8e=1f06+3b9 1f8f=1f07+3b9 1f90=1f20+3b9 ' +
  '1f91=1f21+3b9 1f92=1f22+3b9 1f93=1f23+3b9 1f94=1f24+3b9 1f95=1f25+3b9 1f96=1f26+3b9 ' +
  '1f97=1f27+3b9 1f98=1f20+3b9 1f99=1f21+3b9 1f9a=1f22+3b9 1f9b=1f23+3b9 1f9c=1f24+3b9 ' +
  '1f9d=1f25+3b9 1f9e=1f26+3b9 1f9f=1f27+3b9 1fa0=1f60+3b9 1fa1=1f61+3b9 1fa2=1f62+3b9 ' +
  '1fa3=1f63+3b9 1fa4=1f64+3b9 1fa5=1f65+3b9 1fa6=1f66+3b9 1fa7=1f67+3b9 1fa8=1f60+3b9 ' +
  '1fa9=1f61+3b9 1faa=1f62+3b9 1fab=1f63+3b9 1fac=1f64+3b9 1fad=1f65+3b9 1fae=1f66+3b9 ' +
  '1faf=1f67+3b9 1fb2=1f70+3b9 1fb3=3b1+3b9 1fb4=3ac+3b9 1fb6=3b1+342 1fb7=3b1+342+3b9 ' +
  '1fbc=3b1+3b9 1fbe=3b9 1fc2=1f74+3b9 1fc3=3b7+3b9 1fc4=3ae+3b9 1fc6=3b7+342 1fc7=3b7+342+3b9 ' +
  '1fcc=3b7+3b9 1fd2=3b9+308+300 1fd3=3b9+308+301 1fd6=3b9+342 1fd7=3b9+308+342 1fe2=3c5+308+300 ' +
  '1fe3=3c5+308+301 1fe4=3c1+313 1fe6=3c5+342 1fe7=3c5+308+342 1ff2=1f7c+3b9 1ff3=3c9+3b9 ' +
  '1ff4=3ce+3b9 1ff6=3c9+342 1ff7=3c9+342+3b9 1ffc=3c9+3b9 fb00=66+66 fb01=66+69 fb02=66+6c ' +
  'fb03=66+66+69 fb04=66+66+6c fb05=73+74 fb06=73+74 fb13=574+576 fb14=574+565 fb15=574+56b ' +
  'fb16=57e+576 fb17=574+56d'
).split(' ').map(entry => {
  const [from, to] = entry.split('=');
  return [String.fromCodePoint(parseInt(from, 16)),
    to.split('+').map(code => String.fromCodePoint(parseInt(code, 16))).join('')];
}));

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
  return !row.link || HTTPS_LINK.test(row.link) || TASK_KEY.test(row.link);
}

function taskFields(note) {
  const fields = {'Problem': '', 'Done when': '', 'Out of scope': ''};
  let current;
  for (const line of note.split(/\r?\n/).slice(1)) {
    const header = /^(Problem|Done when|Out of scope):[ \t]*(.*)$/.exec(line);
    if (header) {
      current = header[1];
      fields[current] += '\n' + header[2];
    } else if (current) {
      fields[current] += '\n' + line;
    }
  }
  return Object.fromEntries(Object.entries(fields).map(([name, value]) => [name, value.trim()]));
}

// The form has no title or repo columns, so both come from the "[issue] <repo>: <title>" prefix.
// repo is the full owner/name form, e.g. arii/remote-server.
function taskRecord(note) {
  const [, repo, title] = ISSUE_PREFIX.exec(note);
  const fields = taskFields(note);
  return {
    title: title.trim(), repo: OWNER + '/' + repo,
    problem: fields['Problem'], scope: fields['Out of scope'], done_when: fields['Done when'],
  };
}

function missingFields(record) {
  return REQUIRED_FIELDS.filter(name => !record[name]);
}

function dedupKey(row) {
  const input = row.link || row.source + '|' + row.note;
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, input,
    Utilities.Charset.UTF_8)
    .slice(0, 8).map(byte => (byte & 255).toString(16).padStart(2, '0')).join('');
}

// Mirrors scripts/ledger_intake.py normalize(): NFKC, strip, casefold, collapse whitespace.
function casefold(text) {
  let out = '';
  for (const char of text) {
    const code = char.codePointAt(0);
    if (code >= 0x13a0 && code <= 0x13f5) {
      out += char; // Cherokee folds to uppercase
    } else if (code >= 0x13f8 && code <= 0x13fd) {
      out += String.fromCodePoint(code - 8);
    } else if (code >= 0xab70 && code <= 0xabbf) {
      out += String.fromCodePoint(code - 0xab70 + 0x13a0);
    } else {
      out += CASEFOLD_EXTRA.get(char) || char.toLowerCase();
    }
  }
  return out;
}

function normalize(value) {
  const text = casefold(String(value || '').normalize('NFKC').replace(PY_SPACE_EDGES, ''));
  return text.replace(PY_SPACE_RUNS, ' ');
}

function sha256Hex(text) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, text, Utilities.Charset.UTF_8)
    .map(byte => (byte & 255).toString(16).padStart(2, '0')).join('');
}

// repo must be the full owner/name form, e.g. arii/remote-server.
function dedupeHash(title, repo) {
  return sha256Hex(normalize(title) + '\n' + normalize(repo));
}

function intakeId(title, repo) {
  return 'ledger-intake-' + dedupeHash(title, repo).slice(0, 24);
}

function intakeKeys(row, store) {
  const record = taskRecord(row.note);
  const {title, repo: fullRepo} = record;
  const hash = dedupeHash(title, fullRepo);
  const missing = missingFields(record);
  // Submit never writes READY or DISPATCHED: only Ariel marks work ready and the queue dispatches.
  const status = store.getProperty(HASH_MARKER + hash) ? 'DUPLICATE' : missing.length ? 'NEEDS_INFO' : 'NEW';
  return {intake_id: intakeId(title, fullRepo), dedupe_hash: hash, missing_fields: missing.join(','), status};
}

// Finds the columns by header name, appending any missing header to the right of the existing ones.
function writeIntakeColumns(range, keys) {
  const sheet = range.getSheet();
  const width = Math.max(sheet.getLastColumn(), 1);
  const headers = sheet.getRange(1, 1, 1, width).getValues()[0].map(cell => String(cell).trim());
  const absent = INTAKE_COLUMNS.filter(name => !headers.includes(name));
  if (absent.length) {
    sheet.getRange(1, width + 1, 1, absent.length).setValues([absent]);
    headers.push(...absent);
  }
  const columns = INTAKE_COLUMNS.map(name => headers.indexOf(name));
  const first = Math.min(...columns);
  const rowNumber = range.getRow();
  const span = sheet.getRange(rowNumber, first + 1, 1, Math.max(...columns) - first + 1);
  const values = span.getValues()[0];
  INTAKE_COLUMNS.forEach((name, i) => { values[columns[i] - first] = keys[name]; });
  span.setValues([values]);
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
  if (processRow(row, e.range, store, props) === 'busy') {
    // Concurrency guard: never file without the lock (that is how duplicates happen),
    // and never fail silently either. The row stays unprocessed; resubmitting retries it.
    submitOutcome(e.range, row.source, 'Later', 'Busy: another Ledger submission was being filed. Resubmit to retry.', '');
    console.info('Agent Ledger: lock busy, submission not filed.');
  }
}

// Files one eligible row: writes the intake columns, creates or dedupes the
// GitHub issue, and records the dedupe hash once an issue exists.
// Returns 'busy' when the script lock is held by another run; the caller
// decides whether to report that (form path) or retry later (scan path).
function processRow(row, range, store, props) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(LOCK_WAIT_MS)) return 'busy';
  try {
    // A form submission and a scan tick can race on the same row; if the
    // intake columns are already written, the row is already processed.
    const sheet = range.getSheet();
    const headers = sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1)).getValues()[0]
      .map(cell => String(cell).trim());
    const intakeColumn = headers.indexOf('intake_id');
    if (intakeColumn >= 0 && sheet.getRange(range.getRow(), intakeColumn + 1).getValue()) return 'done';
    const keys = intakeKeys(row, store);
    writeIntakeColumns(range, keys);
    intake(row, range, store, props);
    // Remember the title/repo only once an issue exists, so a failed run is not a duplicate.
    const issueUrl = store.getProperty('created:' + dedupKey(row));
    if (keys.status === 'NEW' && issueUrl) store.setProperty(HASH_MARKER + keys.dedupe_hash, issueUrl);
    return 'done';
  } finally {
    lock.releaseLock();
  }
}

// Adds the manual scan control to the spreadsheet menu bar.
function onOpen() {
  SpreadsheetApp.getUi().createMenu('Agent Ledger')
    .addItem('Process new rows', 'scanPendingRows')
    .addToUi();
}

// Catches rows written directly to the response sheet (Sheets API appends and
// manual edits), which never fire the form-submit trigger. Install as a
// time-driven trigger (daily) and run on demand from the Agent Ledger menu
// in the spreadsheet. The watermark starts at the current
// last row on first run, so historical rows are never scanned; rows the scan
// cannot file get SKIPPED in the hook-owned status column and are not retried.
function scanPendingRows() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  if (!spreadsheet) throw new Error('scanPendingRows must run in the spreadsheet-bound script.');
  const sheet = spreadsheet.getSheets().find(candidate => candidate.getFormUrl()) || spreadsheet.getSheets()[0];
  const store = PropertiesService.getScriptProperties();
  const props = store.getProperties();
  const watermark = Number(store.getProperty(SCAN_WATERMARK) || 0);
  if (!watermark) {
    store.setProperty(SCAN_WATERMARK, String(sheet.getLastRow()));
    console.info('Agent Ledger: scan watermark armed at row ' + sheet.getLastRow() + '.');
    return;
  }
  const headers = sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1)).getValues()[0]
    .map(cell => String(cell).trim());
  const column = name => headers.indexOf(name);
  const lastRow = sheet.getLastRow();
  let processedTo = watermark;
  for (let rowNumber = watermark + 1; rowNumber <= lastRow; rowNumber++) {
    const values = sheet.getRange(rowNumber, 1, 1, headers.length).getValues()[0];
    const cell = name => String(values[column(name)] || '');
    if (cell('intake_id') || cell('status')) {
      processedTo = rowNumber;
      continue;
    }
    const row = {
      source: cell('Agent / Source'), note: cell('Item / Note'), status: cell('Status'),
      link: cell('Link'), timestamp: cell('Timestamp'),
    };
    const range = sheet.getRange(rowNumber, 1);
    if (!eligible(row, props)) {
      writeIntakeColumns(range, {intake_id: '', dedupe_hash: '', missing_fields: '', status: 'SKIPPED'});
      processedTo = rowNumber;
      continue;
    }
    if (processRow(row, range, store, props) === 'busy') break;
    processedTo = rowNumber;
  }
  // Outcome rows appended while scanning land below processedTo's rows but are
  // covered by advancing to the live last row: they are results, not intake.
  store.setProperty(SCAN_WATERMARK, String(Math.max(processedTo, sheet.getLastRow())));
}

function intake(row, range, store, props) {
  const missing = missingFields(taskRecord(row.note));
  if (missing.length) {
    const marker = 'later:' + dedupKey({...row, link: ''});
    if (!store.getProperty(marker)) {
      submitOutcome(range, row.source, 'Later', 'Missing required task field: ' + missing.map(name => FIELD_LABELS[name]).join(', ') + '.', '');
      store.setProperty(marker, 'true');
    }
    return;
  }
  const key = dedupKey(row);
  const marker = 'created:' + key;
  const issueUrl = store.getProperty(marker);
  if (issueUrl) {
    submitDone(range, row.source, key, issueUrl, store);
    return;
  }
  const [, repo, rawTitle] = ISSUE_PREFIX.exec(row.note);
  const token = installationToken(props, repo);
  const repoPath = '/repos/' + OWNER + '/' + encodeURIComponent(repo);
  if (hasLedgerIssue(repo, key, token)) return;

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
  store.setProperty(marker, issue.html_url);
  submitDone(range, row.source, key, issue.html_url, store);
}

function submitDone(range, source, key, issueUrl, store) {
  const marker = 'done:' + key;
  if (store.getProperty(marker)) return;
  submitOutcome(range, source, 'Done', 'issue filed for ' + key, issueUrl);
  store.setProperty(marker, 'true');
}

function hasLedgerIssue(repo, key, token) {
  const marker = 'ledger-key: ' + key;
  const query = 'repo:' + OWNER + '/' + repo + ' is:issue in:body "' + marker + '"';
  const path = '/search/issues?q=' + encodeURIComponent(query) + '&per_page=100&page=';
  let seen = 0;
  for (let page = 1; page <= 10; page++) {
    const search = github(path + page, token);
    if (search.items.some(issue => (issue.body || '').split(/\r?\n/).includes(marker))) return true;
    if (search.incomplete_results) break;
    seen += search.items.length;
    if (seen >= search.total_count) return false;
    if (search.items.length === 0) break;
  }
  throw new Error('GitHub issue search did not complete; no issue created.');
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
    ...Object.entries(taskFields(row.note)).flatMap(([name, value]) => [
      '## ' + name, '', fence + 'text', value || '(not specified)', fence, '',
    ]),
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
