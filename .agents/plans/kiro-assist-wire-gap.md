# /assist wire shape: current build vs the Gemini spec (analysis only)

Source of the spec: the "Gemini wire-shape spec" in `kiro-proofloop-next.md`. Current shape is read from
`proofloop/extension/background.js` (request), `proofloop/harness/page_assist.py` `assist()` (response),
`proofloop/harness/server.py` (`/feedback`) and `proofloop/extension/assist/observer.js` (rendering), at `d071f32`.
Nothing is implemented here.

## How it works today, in one paragraph

The content script (`observer.js`) classifies the page's task locally and asks the background worker for help
whenever the task changes (first scan, or a DOM change that changes the task). The background worker posts to
`/assist` with the bearer token in the `Authorization` header. The response carries rule definitions (with
forbidden values as salted hashes), past-session facts and open-tab matches. **Conflicts are computed in the
browser**: the observer hashes field values locally and compares them with the rules, so the backend never sees a
value and never produces a "warning". Feedback goes to a separate `POST /feedback`.

## Request

| Spec field | Current | Gap | Notes and risk |
|---|---|---|---|
| `token` (in body) | `Authorization: Bearer <token>` header on every API route | Different place | Keep the header. A token in the JSON body is easier to log by accident and needs its own constant-time check. Recommend the spec move it to the header |
| `trigger` (`tab_activated` \| `tab_updated` \| `chip_action` \| `manual_refresh`) | Absent. The call is implicit: the content script calls on task change | Missing | Adding it is cheap. But `tab_activated`/`tab_updated` would mean the background calls `/assist` itself on tab events. Today `onActivated`/`onUpdated` only update the in-memory snapshot. That is a behavior change: more calls, and calls for tabs with no content script |
| `active_tab.tab_id` | Not sent (the background knows `sender.tab.id`) | Missing | Harmless locally. The backend has no use for it except caching or debugging |
| `active_tab.url` | Not sent. Only `origin` (scheme + host + port) | **Conflict** | Full URLs carry paths, query tokens and fragments. Security plan S1 and the current contract test (`test_background.cjs`) require origin only. Sending `url` would also reach Cognee when recall is on |
| `active_tab.origin` | `origin` (top level) | Renamed or nested | Shape change only |
| `active_tab.title` | Not sent for the active tab | **Conflict (partial)** | Titles of other tabs are already sent, cut to 80 characters (`open_tabs`). Adding the active title is a smaller step, but it still widens S1 and the background contract |
| `active_tab.is_terminal` | Computed in the content script (`location.port === "8082"` or xterm DOM), not sent | Missing on the wire | Only needed if the server should answer differently for terminals. Today the client decides rendering |
| `active_tab.context_hint` (optional) | Not sent. The nearest thing is `task` | Missing / different | Undefined in the spec. If it means page text, it conflicts with "no page text". If it means the task, it already exists |
| (not in spec) `task` | Sent: the locally classified task id | **Spec lacks it** | Required. Rules are scoped by task (milestone M4). Dropping it would serve every rule on every page, which the assist eval would catch as false positives |
| (not in spec) `recall` | Sent: boolean, from the Cognee page-recall setting | Spec lacks it | Needed to keep Cognee page recall opt-in |
| `open_tabs[].tab_id` | Not sent | Missing | Harmless |
| `open_tabs[].url` | Not sent; `origin` only | **Conflict** | Same as `active_tab.url`. Other tabs are often banking, mail or private dashboards |
| `open_tabs[].origin` | Sent | Matches | |
| `open_tabs[].title` | Sent, cut to 80 chars, at most 10 tabs from the browser (the server caps at 12), most recently active first | Matches (with caps) | The spec does not say whether there are caps; keep them |
| `open_tabs[].is_terminal` | Not sent | Missing | Would need the background to detect terminals without a content script (by port only) |
| `open_tabs[].last_active_ts` | Kept in the background snapshot (`TABS.at`) and used for ordering; not sent | Missing on the wire | Cheap to add; minor timing fingerprint, no content |
| `feedback` (`action` `apply` \| `keep` \| `dismiss` \| `null`, `item_id`, `observed_value`) | Separate `POST /feedback {rule_id, action}` with `action` in `shown` \| `dismissed` \| `rule_wrong` | **Different endpoint and vocabulary; two conflicts** | `apply` conflicts with the observer rule (M3: never fills or changes a field). `observed_value` conflicts with "field values never leave the browser" (README, `test_security.py`, `e2e` asserts feedback carries no values). Mapping: `dismiss` → `dismissed`; `keep` ≈ `dismissed` (kept the value); `rule_wrong` has no spec equivalent but feeds the mutator (`replay_loop.read_feedback`); `shown` has no spec equivalent |

## Response

| Spec field | Current | Gap | Notes |
|---|---|---|---|
| `active_skill_version` | `version` (`"v3"` or `null`) | Renamed | Shape change only |
| `senso_synced` (boolean) | `source.kind`: `senso` (node read back and hash-checked), `senso-copy` (node id known, Senso not enabled on this host), `senso-mismatch`, `local`, `none`, `invalid`, plus `source.label` and `source.node_id` | Derivable, lossy | `senso_synced = source.kind == "senso"`. A boolean loses "stored but not re-read here" versus "not in Senso at all"; keep `source` alongside |
| `loop_status.state` (`idle` \| `running` \| `rolled_back`) | Not in `/assist`. `/augment` (dashboard) has `active_version`, `scores`, `stop` and the ledger history | **Missing; `running` is not knowable today** | `rolled_back` can be derived from the last ledger entry (`status` `rejected`). `idle` is the default. `running` needs the loop to publish a heartbeat or lock file. Today it writes only the ledger and `last_run.json` at the end of each cycle or run. That would be a new state file, not a ledger or gate change, but it is loop code |
| `loop_status.last_delta` | Last ledger entry `gate.train_gain` (or `scores` before vs after) | Derivable | Holdout delta is also available (`gate.holdout_before/after`) |
| `loop_status.last_gate_decision` | Last ledger entry `gate.choice` (`promote` \| `hold` \| `reject`) and `status` (incl. `invalid_proposal`, `promotion_failed`) | Derivable | Spec values are not defined; map from `choice` |
| `items[]` | Three lists: `page_rules` (rule definitions for the task), `context` (past-session facts for this origin or task, plus Cognee recall), `tab_matches` (other open tabs that touch recorded sessions) | **Different model** | The spec's `items` are display items. Current lists are inputs the observer turns into display items |
| `items[].kind = warning` | Not produced by the server. Conflicts are computed in the browser from `page_rules` plus local field values | **Cannot be server-side without values** | The server never sees field values, so it cannot know a value conflicts. A server `warning` item would need `observed_value` (conflict above). Keep warnings client-side; the server can only send the rule |
| `items[].kind = cross_tab_match` | `tab_matches[]` (origin, title, sessions[]) and, separately, client-side cross-tab value conflicts (hash comparison in the background, `observe` message, off by default) | Partial / split | Server matches are about sessions; value conflicts are local only |
| `items[].kind = session_rule` | `page_rules[]` (rule + message) and `context[]` (session fact) | Partial | Two current lists map to one kind |
| `items[].id` | `page_rules[].id` (rule id); `context[].session_id`; tab matches have no id | Partial | Needs a stable id per display item; `rule_id` must stay because `/feedback` and the mutator key on it |
| `items[].severity` (`info` \| `warn`) | Absent; the client decides (conflict → warning style, everything else plain) | Missing | Derivable: rule with a local conflict → `warn`, otherwise `info` |
| `items[].summary` | `page_rules[].message`, `context[].fact`, `tab_matches[].sessions[].fact` | Renamed | |
| `items[].citation` (`source`, `ref`) | Rules: `provenance` (session ids) plus top-level `source` (kind, label, Senso node id). Context: `source` ("Session log" or "Cognee recall"), `session_id`, `date`, `why` | Partial | `source`/`ref` can be filled from these. Today the citation is split between the item and the top-level `source` |
| `items[].actions` | Absent; the client hardcodes "Got it" and "Rule is wrong" (and "Back to form" and "Submit anyway" for a held submit) | Missing; one conflict | If actions include `apply`, it conflicts with the observer rule |
| (not in spec) `page_rules[].forbid[].sha256`, `field`, `terms`, `match`, `kind`, `tasks` | Sent | **Spec lacks the matching payload** | Without it the browser cannot detect conflicts locally. Adopting the spec as written would remove the core feature unless values go to the server |
| (not in spec) `sha256`, `task`, `recall`, `promoted_at`, `cached` | Sent | Spec lacks them | `sha256` and `source` back the "Senso rule" citation; `cached` marks backend-offline answers |

## Terminal tab (`127.0.0.1:8082`)

| Spec | Current | Gap |
|---|---|---|
| Extra-light corner chip only | Terminal detected by port 8082 or xterm DOM. Pill only, no inline markers, no submit hold, no field scanning | Matches |
| Renders loop status | Pill shows "ProofLoop · N matches" (session context plus tab matches); no loop status | Missing; needs `loop_status` in the response (above) |
| One-line reminders | Panel (on click) lists past-session facts and tab matches; no one-line reminder in the chip itself | Partial |
| Never covers the prompt | Pill placement avoids controls (inputs, buttons, links). An xterm canvas is not an input, so the pill can overlap terminal output; not checked on a live ttyd page | Untested on a real terminal |

## Brief for the milestone check-in

1. **Adopt without conflict** (shape only): `trigger`, `tab_id`, `last_active_ts`, `is_terminal`, `active_skill_version`, `senso_synced` (next to `source`), `items[]` as a display view with `id`, `severity`, `summary`, `citation`, and `loop_status.last_delta` / `last_gate_decision` / `rolled_back` derived from the ledger.
2. **Needs a decision because it conflicts with the security plan or the observer rule:** `url` and `title` for tabs, `observed_value`, the `apply` action, a token in the body. The current build refuses all four on purpose. Each is pinned by a test (`test_background.cjs` request body, `test_security.py` no-leak, e2e "feedback carries no values", observer source rule "never writes to page fields").
3. **Needs new loop code:** `loop_status.state = running`. That means a heartbeat or lock file written by `replay_loop.py`. No gate or ledger schema change is required.
4. **The spec must keep** `task`, `recall`, and the hashed matching payload in rules. Without them, task scoping (M4) and local conflict detection (M2/M3) stop working.
5. **Behavior change hidden in `trigger`:** calling `/assist` from tab events in the background (not only from content scripts) adds calls for tabs that have no observer. Decide whether those tabs should get anything.
