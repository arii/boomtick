# Agent Ledger issue hook

This Sheet-bound Apps Script files issues on `arii` repositories from explicitly opted-in Agent Ledger Form submissions. It never assigns the `ready` label or runs submitted instructions. Eligible submissions are copied into public GitHub issues, so do not include secrets or private information.

## Filing a task (for agents)

Agents file work with one Form response via BoomTick's `scripts/agent_ledger.py post`: Agent / Source set to an allowlisted name, Status `Act`, and an Item / Note shaped like this:

```text
[issue] remote-server: Show queue errors on the Now view
Problem: When a queue run fails, the Now view still says "running".
Done when: A failed run shows "failed" with the run time on Now within one refresh.
Out of scope: No new panels, badges or text beyond the status word.
```

Five fields are required, everywhere (`missing_fields`, issue creation and the skill): `title`, `repo`, `problem`, `scope` and `done_when`. `title` and `repo` come from the first line (the form has no separate title or repo columns, so the parsed `[issue] <repo>: <title>` prefix is the source). The note sections map as `Problem:` to `problem`, `Out of scope:` to `scope` and `Done when:` to `done_when`. Each must have a nonempty value, on the same line or following lines. Use these exact section names at the start of a line. A missing or empty required field creates no issue and posts one `Later` response naming the missing field(s); resubmitting the same source/note does not repeat that response. Behavior change: `Out of scope:` used to be optional and now blocks issue creation like `Problem:` and `Done when:` (write `Out of scope: None.` if nothing is excluded). The issue body includes all three sections and retains the original submission as untrusted text. Only Ariel adds `ready`, and the S5 queue works only `ready` issues. Step-by-step instructions, including what not to file, are in the [`agent-ledger-intake` skill](../../.agents/skills/agent-ledger-intake/SKILL.md).

## Intake columns

For every eligible submission, `onFormSubmit` writes four values on the submitted response row, in one batched write inside the script lock. The columns are found by header name. Any missing header is added to the right of the existing columns, so later Form edits do not shift them. Ineligible submissions are ignored and get no values.

| Column | Value |
| --- | --- |
| `intake_id` | `ledger-intake-` plus the first 24 hex characters of `dedupe_hash` |
| `dedupe_hash` | SHA-256 hex (64 characters) of `normalize(title) + "\n" + normalize(repo)`, UTF-8 |
| `missing_fields` | Comma-separated required fields that are empty, in the canonical order `title`, `repo`, `problem`, `scope`, `done_when`. Empty when complete |
| `status` | `NEW`, `NEEDS_INFO` or `DUPLICATE` |

`title` is the text after `[issue] <repo>:` and `repo` is the full `arii/<repo>` form (for example `arii/remote-server`) in the record, the hash and everywhere else. Callers computing the same hash elsewhere must pass the same full form. `normalize` matches `normalize()` in `scripts/ledger_intake.py` in `arii/remote-server`: NFKC, strip, Unicode full case fold, then each whitespace run becomes one space. The JS casefold is `toLowerCase()` per code point plus a table of the full folds Python applies that `toLowerCase()` does not (for example `ß` to `ss`, final sigma `ς` to `σ`, Cherokee to uppercase). `tests/fixtures/agent-ledger/intake-hash-vectors.json` holds Python-generated vectors that the unit test checks.

The reference is Python 3.11 (Unicode 14.0.0). The vectors use only code points assigned in Unicode 14, and the casefold table above was generated under that version. When the Python or Apps Script (V8) runtime is upgraded, re-run the full code-point check, which compares `normalize()` in `Code.gs` with Python on every assigned code point and re-checks the vectors:

```sh
python3.11 apps-script/agent-ledger-hook/check_unicode_parity.py
```

It exits 1 on any difference or on an unassigned code point in the vectors. Fix differences by extending the casefold table, not by changing the reference.

Submit writes only three statuses:

- `NEEDS_INFO`: any of the five required fields is empty (the same list that blocks issue creation).
- `DUPLICATE`: an earlier submission with the same `dedupe_hash` already has a filed issue. This status does not change issue creation, which still uses the dedup key below, so a reworded note with the same title is marked `DUPLICATE` and still files an issue.
- `NEW`: complete and not a duplicate.

The hook never writes `READY` or `DISPATCHED`. The S5 queue takes work from open GitHub issues with the `ready` label, not from Sheet status values. Only Ariel adds that label.

## Install

1. As the Sheet owner, open the Agent Ledger response spreadsheet. Choose **Extensions → Apps Script**. Paste `Code.gs` into the editor. Under **Project Settings**, show the `appsscript.json` manifest and replace it with the manifest here. Alternatively, with the Apps Script API enabled and `clasp` installed and logged in, run `clasp clone <scriptId>` in an empty local directory, copy in these two files, and run `clasp push` from that directory. Obtain the script ID from the bound project's **Project Settings**.
2. In **Project Settings → Script Properties**, add the following. The App must be installed on every allowlisted repository and grant Issues read/write permission. If reusing a more broadly installed or privileged App, note that each run requests a token for only its target repository and only Issues write and Metadata read. The App's private key itself still has the App's full authority.

   | Property | Value |
   | --- | --- |
   | `GITHUB_APP_ID` | GitHub App ID |
   | `GITHUB_APP_INSTALLATION_ID` | App installation ID for `arii` |
   | `GITHUB_APP_PRIVATE_KEY` | App's unencrypted PKCS#8 PEM private key; newlines or literal `\n` separators |
   | `ALLOWED_SOURCES` | Comma-separated exact values, e.g. `Instinct,Gemini,Antigravity,Kiro,S5-Local` |
   | `ALLOWED_REPOS` | Comma-separated short names, e.g. `remote-server,boomtick,posture-guard` |

   Apps Script expects `BEGIN PRIVATE KEY`. If the GitHub key starts with `BEGIN RSA PRIVATE KEY`, convert it in a trusted environment with `openssl pkcs8 -topk8 -nocrypt -in <github-app-key.pem>` and transfer the result securely. Keep the PEM only in Script Properties, never in the Sheet, Form, logs, or repo. Treat project editors as trusted: they can read Script Properties. Rotate the key in GitHub and replace it in Script Properties. Installation tokens are not stored.
3. Run `selfTest` from the editor and authorize the project. It mints a scoped token and reads the GitHub installation repositories for each allowlisted repo; it does not create issues or modify the ledger. Check the execution log for each repo.
4. Under **Triggers → Add Trigger**, select `onFormSubmit`, **From spreadsheet**, **On form submit**, then save. Install exactly one trigger as the Sheet owner. Do not run `onFormSubmit` from the editor.

## Live verification

Required-field source merged in [#1394](https://github.com/arii/boomtick/pull/1394). Revision [`9d85425`](https://github.com/arii/boomtick/commit/9d85425f59712851aa048a453e5473c8ad7c5577) was deployed to the Sheet-bound hook. The [live evidence](https://github.com/arii/boomtick/issues/1402#issuecomment-7100215675) shows a valid submission created one issue (no `ready` label) and one `Done` row, and a whitespace-only `Done when:` created no issue and one named `Later` row.

Full live acceptance is still open in [#1402](https://github.com/arii/boomtick/issues/1402): other missing and blank cases, rejected replay, duplicate rejection and the concurrency guard. Only an authorized live check should submit through the Form; use data suitable for a public issue. A Sheet edit or a local test does not exercise the live trigger.

If the issue was created but the `Done` response failed, resubmit the same data to retry the response without opening another issue.

Only `Act` submissions with an allowlisted source, an allowlisted repo in the prefix and an empty or HTTPS link are eligible. The first line of the note supplies the title; the full note and link go in the issue. The dedup key is the first 16 hexadecimal characters of SHA-256 over the exact link, or over `source|note` when the link is blank. The hook never fetches submitted links. The Form is not an authentication boundary. There is no daily filing cap. Instead a concurrency guard serializes filing: each submission holds the script lock for its whole check-and-create (dedup marker, title hash and the GitHub search for an existing ledger issue). A submission that can't get the lock within 30 s files nothing and posts one `Later` reply starting `Busy:`; resubmitting retries it. A `MAX_ISSUES_PER_DAY` Script Property, or a leftover `intake-day` property, is ignored. Failed executions appear under **Executions** in Apps Script.

## Rows written directly to the Sheet

Form submissions are processed immediately by the `onFormSubmit` trigger. Rows written directly to the response Sheet (Sheets API appends by Drive-connected agents, manual edits) never fire that trigger, so `scanPendingRows` processes them through the same `processRow` filing path:

- Install `scanPendingRows` as a time-driven trigger (daily). The spreadsheet also gains an **Agent Ledger** menu (`onOpen`) with **Process new rows** for an on-demand run of the same scan.
- A `LAST_SCANNED_ROW` script property is the high-water mark. On first run it is armed at the current last row, so historical rows are never scanned. To process a known set of rows below the current end of the sheet, set `LAST_SCANNED_ROW` to the row just before them before the first run.
- Rows above the watermark with intake columns already written are skipped. Rows that are not eligible intake rows get `SKIPPED` in the hook-owned `status` column and are never retried. Eligible rows are filed exactly like form submissions, under the same script lock, and the watermark advances only past rows actually processed; outcome rows appended during a scan are covered so they are not scanned as intake.
- The `Link` column may hold an `https://` URL or a `task-<key>`; both are accepted by `eligible()` and both feed the same dedupe key.
