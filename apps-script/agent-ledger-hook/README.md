# Agent Ledger issue hook

This Sheet-bound Apps Script files issues on `arii` repositories from explicitly opted-in Agent Ledger Form submissions. It never assigns the `ready` label or runs submitted instructions. Eligible submissions are copied into public GitHub issues, so do not include secrets or private information.

## Filing a task (for agents)

Agents file work with one Form response: Agent / Source set to an allowlisted name, Status `Act`, and an Item / Note shaped like this:

```text
[issue] remote-server: Show queue errors on the Now view
Problem: When a queue run fails, the Now view still says "running".
Done when: A failed run shows "failed" with the run time on Now within one refresh.
Out of scope: No new panels, badges or text beyond the status word.
```

`Problem:` and `Done when:` must each have a nonempty value, on the same line or following lines. `Out of scope:` is optional. Use these exact field names at the start of a line. A missing or empty required field creates no issue and posts one `Later` response naming the missing field(s); resubmitting the same source/note does not repeat that response. The issue body includes all three sections and retains the original submission as untrusted text. Only Ariel adds `ready`, and the S5 queue works only `ready` issues. Step-by-step instructions, including what not to file, are in the [`agent-ledger-intake` skill](../../.agents/skills/agent-ledger-intake/SKILL.md).

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
   | `MAX_ISSUES_PER_DAY` | Maximum new issues per UTC day; defaults to `5` |

   Apps Script expects `BEGIN PRIVATE KEY`. If the GitHub key starts with `BEGIN RSA PRIVATE KEY`, convert it in a trusted environment with `openssl pkcs8 -topk8 -nocrypt -in <github-app-key.pem>` and transfer the result securely. Keep the PEM only in Script Properties, never in the Sheet, Form, logs, or repo. Treat project editors as trusted: they can read Script Properties. Rotate the key in GitHub and replace it in Script Properties. Installation tokens are not stored.
3. Run `selfTest` from the editor and authorize the project. It mints a scoped token and reads the GitHub installation repositories for each allowlisted repo; it does not create issues or modify the ledger. Check the execution log for each repo.
4. Under **Triggers → Add Trigger**, select `onFormSubmit`, **From spreadsheet**, **On form submit**, then save. Install exactly one trigger as the Sheet owner. Do not run `onFormSubmit` from the editor.

## Live verification

Submit via the Form, not by editing a Sheet row: take an allowlisted source and use `Act` with the complete shape above and a unique smoke-test title. Check that one issue with `ledger-intake` and `insight` (not `ready`) is created, and that a `Done` response appears in the Sheet with the issue URL. Submit the same data again and verify no second issue is created. Only use test data suitable for a public issue.

Also submit a unique note missing `Problem:` or `Done when:` and check that no issue is created and exactly one `Later` response names the missing field. Repeat it to check that the response is not duplicated. Repeat with an empty required value. These checks require deploying this script version first.

If the issue was created but the `Done` response failed, resubmit the same data to retry the response without opening another issue.

Only `Act` submissions with an allowlisted source, an allowlisted repo in the prefix and an empty or HTTPS link are eligible. The first line of the note supplies the title; the full note and link go in the issue. The dedup key is the first 16 hexadecimal characters of SHA-256 over the exact link, or over `source|note` when the link is blank. The hook never fetches submitted links. The Form is not an authentication boundary. The cap is shared across repositories; the first eligible submission skipped by the cap posts one `Later` response that day. Failed executions appear under **Executions** in Apps Script.
