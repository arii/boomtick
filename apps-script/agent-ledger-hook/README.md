# Agent Ledger issue hook

This Sheet-bound Apps Script files issues on `arii` repositories from explicitly opted-in Agent Ledger Form submissions. It never assigns the `ready` label or runs submitted instructions. Eligible submissions are copied into public GitHub issues, so do not include secrets or private information.

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

Submit via the Form, not by editing a Sheet row: take an allowlisted source and use `Act` with a unique note such as `[issue] remote-server: Agent Ledger hook smoke test`. Check that one issue with `ledger-intake` and `insight` (not `ready`) is created, and that a `Done` response appears in the Sheet with the issue URL. Submit the same data again and verify no second issue is created. Only use test data suitable for a public issue.

Only `Act` submissions with an allowlisted source, an allowlisted repo in the prefix and an empty or HTTPS link are eligible. The first line of the note supplies the title; the full note goes in the issue. The hook never fetches submitted links. The Form is not an authentication boundary. The cap is shared across repositories; the first eligible submission skipped by the cap posts one `Later` response that day. Failed executions appear under **Executions** in Apps Script.
