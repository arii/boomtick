# TokensWithTaste

A local OpenAI-compatible chat gateway with an ordered `httpx` waterfall,
live catalog discovery, SQLite traces, and actionable token audits. No LiteLLM
runtime dependency, Router, or proxy: its pinned price map is **data only**.
Python 3.11+.

## Quick start

```sh
cd tokens-with-taste
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
# Export only keys you actually have. .env.example is NOT loaded automatically.
export GROQ_API_KEY='your-key'
twt sync
twt models --free --tools
twt serve
# Another terminal:
curl -i http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'X-Privacy: strict' -H 'X-Session-Id: my-task' \
  -d '{"model":"default","messages":[{"role":"user","content":"Hello"}]}'
```

Gateway: **127.0.0.1:8000/v1**, including `GET /v1/models` and
`POST /v1/chat/completions`. `serve --port` changes the port, not the bind address.
`model: default` and `route:default` select the waterfall; an exact catalog ID
or `provider/id` restricts selection to that model. `stream` is always forced
to `false`. This is a single-process local tool, not a public authenticated proxy.

### Run without API keys (Ollama)

Install [Ollama](https://ollama.com/download) (verified with 0.17.7). Start it
on `127.0.0.1:11434` with `OLLAMA_NO_CLOUD=1`. If Ollama runs as a background
service, [configure that service and restart it](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features)
instead of starting a second server.

```sh
ollama pull qwen2.5:0.5b
export TWT_OLLAMA_MODEL=qwen2.5:0.5b
twt sync
twt serve
# From another terminal, send the same curl request as above.
```

Use the same `TWT_OLLAMA_MODEL` for both sync and serve. This selects only the
named local model, even if hosted credentials are set. Sync requires the model
to support chat; the gateway verifies cloud is disabled before sending prompts
and never falls back to a hosted provider in this mode. Tools are offered only
if Ollama advertises them; structured output is not enabled in local mode.
Context audits use the running model's context limit when available and the
model's advertised maximum otherwise.
Reported API cost is zero when usage is known; this excludes local compute.
Unset `TWT_OLLAMA_MODEL` to restore the hosted waterfall.

### Audit commands

```sh
twt sync                           # live REST discovery + metadata, no fake responses
twt models --free --tools          # chat, free-eligible, tool-capable intersection
twt audit --flagged                # JSON lines, trace IDs and flags
twt inspect TRACE_ID               # Markdown prompt/tokens/attempts/response diagnostic
twt report                         # JSON spend/calls/tokens/flags per route/provider/model
twt report --since 2026-11-16       # UTC date or ISO timestamp (inclusive)
twt --db /path/to/private.db report # --db is a global option
python -m pytest -v
```

Default database: `~/.local/share/twt/catalog.sqlite3`; override with `TWT_DB`
or `--db`. It contains **full prompts and responses**, including tool arguments.
New directories are private and the database is chmod 0600. Protect backups,
and do not share `inspect` output without checking its contents. HTTP
authorization headers and credential values are never saved. There is no
automatic trace deletion or redaction.

## Routing, limits and costs

Configured provider order: **Google, Groq, NVIDIA, Mistral, OpenRouter,
SambaNova, Cloudflare, Nebius**. It is the tie-break for the cost ordering below. Google, Groq, NVIDIA, OpenRouter, SambaNova and
Cloudflare select only verified free-eligible models by default. Mistral is
metered and requires API billing access; free Studio/playground access does
not provide API access. Nebius is also a paid fallback. Unknown free-tier
eligibility is not assumed. Explicit model requests may select a paid model.
Within a provider, selection is deterministic: free first, then lowest known
blended price, then input price, then ID. One matching model is attempted per
provider. Across providers that can be called, attempts are ordered free first
(in configured provider order), then paid by that provider's best blended price
(`0.8 * input + 0.2 * output` per token), then providers whose paid price is
unknown. Ties keep configured order. Providers skipped without a call (disabled,
missing credentials, strict privacy, no eligible model) keep their configured
position, so their skip reasons appear in the same place in the trace.

For accounts without access to a provider, set `TWT_DISABLED_PROVIDERS` to a
comma-separated list of provider IDs, for example `TWT_DISABLED_PROVIDERS=mistral`.
Exclusions override credentials, cached catalog rows, per-provider model pins and
explicit model requests. Disabled providers are not contacted for catalog sync
or inference and are hidden from model listings; cached rows are retained for
history, not deleted. Unknown IDs fail closed to catch misspellings. Apply the
setting to the gateway process (including service adapters that pass an explicit
provider configuration), not only to the calling client. This does not change
paid budgets or turn another provider into free capacity. A source change alone
does not update an installed/running service.
This excludes only provider API traffic. It does not block Mistral websites,
remove separate browser-based access, or establish that a web adapter/login works.

`X-Privacy: strict` permits **only Groq and Cloudflare** in hosted mode, excludes training
providers, and otherwise follows the same filters. Unknown policy values are JSON `null`.
Groq may retain reliability/abuse logs unless account ZDR is enabled.

Before calling, the gateway checks credentials (recording missing env names),
privacy, synced chat modality, requested model, tools, JSON/JSON-schema
capability, budget, cooldown, then RPM. Unknown chat/tool/JSON support fails
closed. OpenRouter `:free` or zero price alone is **not** chat/tool evidence:
`architecture.output_modalities` and `supported_parameters` are checked.
Other providers use exact-ID OpenRouter cross-references or exact LiteLLM
provider/model entries for capabilities; no fuzzy name matching. Non-OpenRouter
prices come only from that provider's LiteLLM entry, never another provider's
OpenRouter marketplace price. Missing capabilities remain
unknown/unsupported. `response_format.type=json_schema` needs schema support.

After HTTP 502, 503, 504 or 529 the provider/model gets an
`overload cooldown`: `Retry-After` seconds when sent, else 30, capped at 300
(an unparseable `Retry-After` counts as 60, as for 429). Other 5xx such as 500
set no cooldown, because one bad request can cause them.
Later requests skip it with that reason instead of calling again; free models
are not waited for. Ranking ignores cooldowns, so a cooled cheapest provider
still appears first in the trace as a no-call attempt. Paid cost of the failed attempt stays unknown, never zero.
Paid transport timeouts set no cooldown.

Routed requests fall through on upstream HTTP errors, transport failures and
malformed chat responses. Pinned requests still return non-retryable 4xx errors.
429 starts a per-provider/model cooldown using numeric or HTTP-date
`Retry-After` (60 seconds if absent/invalid). If a route exhausts its eligible
providers due only to upstream rate limits, TwT waits for the shortest cooldown
within the remaining wait budget and retries the waterfall once, without
bypassing cooldowns. Exhausted-route errors include `rate_limited_only`.
`TWT_FREE_WAIT_SECONDS` sets the per-request wait budget (0–60 seconds, default
60). A local 60-second sliding-window
counter includes every actual attempt, not skips. Configured RPM: Groq's two
listed GPT OSS models 30, OpenRouter **`:free` only** 20, listed SambaNova
models 20, Cloudflare non-paid text default 300 (no models yet verified).
**No local cap is configured for undocumented limits**. Daily values are
catalog metadata, not locally enforced; actual provider/account quotas remain
authoritative. RPM and cooldown state reset on restart. Run one server/worker.
A short lock protects the budget/cooldown check and RPM slot reservation;
upstream HTTP calls run concurrently outside that lock.

Optional `TWT_DAILY_BUDGET_USD` is a finite nonnegative number. Once recorded
UTC-day spend reaches it, paid models are skipped, while free models remain
eligible. Paid models with unknown prices are also skipped when a budget is
configured. This is a **pre-check**, not a reservation or billing hard cap:
in-flight requests can cross the threshold, and external usage is not visible.
An exhausted waterfall returns an error with every skip/failure reason,
including every missing credential env var. No mock completion is available.

Response headers: `X-Trace-Id`, `X-Provider-Used`, `X-Cost-Usd`,
`X-Audit-Flags` (comma-separated; empty when clean). Cost is a token-price
estimate, **not an invoice**: prompt tokens × input price + completion tokens
× output price. Cache discounts, separate reasoning rates, media/request fees,
taxes and subscription charges are not modeled. Unknown prices return
`X-Cost-Usd: unknown` and SQLite `cost_usd: null`, never fabricated zero.
`known_cost_usd` always retains the sum of known attempt costs, including failed
attempts; `cost_complete` is false if any called attempt is unpriced or lacks
usage. Budget checks count that known sum even when the total is incomplete.
Free costs assume the documented free/evaluation tier; verify your account tier before
using a paid key. Account eligibility and remaining free quotas cannot be
inferred from a model list. Reports show unknown-cost call counts separately.
NVIDIA models are marked free-eligible and their prices are zeroed because
NVIDIA documents free hosted prototyping access, not because the catalog proves
this account has that entitlement. Account entitlement remains unverified.

## Trace schema and audits

SQLite `models` stores a provider/ID registry; `traces` stores each trace's JSON
with ID, UTC timestamp, requested route, privacy, session ID, final/last-called
provider and model, status, latency, tokens (prompt/completion/reasoning/visible),
cost, flags, full request and response. Each attempt is also stored separately
in `attempts(trace_id, ordinal, data)`: provider/model, timestamp, called/skip,
reason, HTTP status, latency, full sent payload/received payload, tokens and
cost. Skips are retained too. `tool_calls` stores canonical signatures scoped
by session. Authorization is never part of recorded payloads.

| Flag | Exact trigger | Report recommendation |
|---|---|---|
| EXCESSIVE_REASONING | reasoning > 3 × visible tokens; visible = max(0, completion − reasoning) | lower reasoning effort or cap max_tokens |
| TOOL_CALL_LOOP | repeated function name + canonical JSON arguments in the same explicit `X-Session-Id` | deduplicate tool calls |
| CONTEXT_BLOAT | prompt > 32,000 tokens or > 80% of known context window | trim/summarize history |
| FALLBACK_CASCADE | more than one actual upstream call (skips alone do not count) | repair/deprioritize the provider with most failures, with reasons |
| TRUNCATED_MAX_TOKENS | any choice has `finish_reason: length` | raise max_tokens or shorten the task |

Session IDs must be stable for one task and different for unrelated tasks.
Without a session ID, tool signatures are not compared across requests.
Providers that omit usage cannot yield a reliable usage/cost audit; missing
counts are null, never invented token estimates. Reports separately count
unknown-usage calls. Trace-level token fields describe the final successful
completion; attempts retain usage from unsuccessful providers too.
Report totals aggregate spend and tokens per actual attempt's provider/model,
including failed attempts. Group calls count upstream attempts, not skips;
group flag counts count affected traces once per provider/model, while overall
flag counts count traces once. Traces with only skips contribute no spend rows.

## Catalog sources

`twt sync` in hosted mode fetches [OpenRouter's public catalog](https://openrouter.ai/api/v1/models)
and the [pinned LiteLLM map](https://raw.githubusercontent.com/BerriAI/litellm/d034fb681ca296a0f082a224043eda62a2ce82d4/model_prices_and_context_window.json).
Pin: **d034fb681ca296a0f082a224043eda62a2ce82d4**. It then polls credentialed
provider `/models` endpoints; NVIDIA and SambaNova lists also work publicly.
OpenRouter needs no key for discovery, but **does** need one for inference.
Missing keys skip authenticated discovery with explicit env names. Per-provider
listing errors preserve that provider's cache; a successful empty listing
clears it. Global source fetch errors fail sync without replacing the catalog.
Catalogs may be stale: refresh before use. Provider endpoint paths that are not
verified are blocked instead of guessed.

Map fields used: `mode`, `max_input_tokens`, `input_cost_per_token`,
`output_cost_per_token`, `supports_function_calling`, `supports_response_schema`.
OpenRouter fields used: `id`, `pricing.prompt`, `pricing.completion`,
`context_length`, `architecture.output_modalities`, `supported_parameters`
(`tools`, `response_format`, `structured_outputs`). The map's
`supports_tool_choice`, parallel-tool and specialized-price fields exist but
are not used to claim unsupported guarantees. LiteLLM data is third-party
metadata, not live authenticated capability or pricing verification.

## Provider verification table

**All checked 2026-11-16.** Sources below are public provider documentation
unless labeled otherwise. Prices are USD per million tokens, input/output,
unless stated otherwise. `providers.json` carries checked/source provenance;
env names are this project's configuration convention, not remotely discovered
values. No provider credentials were available. A public model-list success
does not prove unauthenticated inference or account-specific availability.

| Provider / base URL / env | Verified models, prices and limits | Privacy / source / unauthenticated probe |
|---|---|---|
| Google: `https://generativelanguage.googleapis.com/v1beta/openai`; `GOOGLE_API_KEY` | `gemini-3.1-flash-lite`: free input/output; paid $0.25/$1.50 text. Numeric limits unset. [Pricing](https://ai.google.dev/gemini-api/docs/pricing), [limits](https://ai.google.dev/gemini-api/docs/rate-limits) | Free data “Used to improve our products: Yes”; non-strict. [Compatibility](https://ai.google.dev/gemini-api/docs/openai). Compatible `/models` **404**, native `/v1beta/models` **403**. |
| Groq: `https://api.groq.com/openai/v1`; `GROQ_API_KEY` | `openai/gpt-oss-20b`, `openai/gpt-oss-120b`: free table **30 RPM / 1000 RPD** each. Listed paid prices $0.075/$0.30 and $0.15/$0.60. [Limits](https://console.groq.com/docs/rate-limits), [models](https://console.groq.com/docs/models) | Strict eligible; [agreement §4.2](https://console.groq.com/docs/legal/services-agreement) prohibits training without permission. [Retention caveats](https://console.groq.com/docs/your-data). [Compatibility](https://console.groq.com/docs/openai). `/models` **403**, `error code: 1010` (not a clean auth test). |
| NVIDIA: `https://integrate.api.nvidia.com/v1`; `NVIDIA_API_KEY` | Live catalog IDs only; no pinned model IDs. Developer Program free prototyping per [product docs](https://docs.api.nvidia.com/nim/docs/product). Numeric limits unset: [FAQ](https://forums.developer.nvidia.com/t/nvidia-nim-faq/300317) says they vary. | Non-strict; [trial terms §3.3](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf): content may improve products including AI models. [OpenAI example](https://docs.api.nvidia.com/nim/reference/deepseek-ai-deepseek-v4-flash-infer). `/models` **200**, observed 39 models. |
| Mistral: `https://api.mistral.ai/v1`; `MISTRAL_API_KEY` | Free-model eligibility, prices and numeric limits unset. `mistral-small-latest` is a [quickstart example](https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key.md), not proof of free eligibility. [Limits](https://docs.mistral.ai/admin/billing-usage/usage-limits.md) are account/model-specific. | Non-strict; [Free-mode training policy](https://help.mistral.ai/en/articles/347617-do-you-use-my-user-data-to-train-your-artificial-in) allows training with opt-out; [ZDR](https://docs.mistral.ai/admin/monitor-comply/zero-data-retention.md) paid only. `/models` **401** `{"detail":"Invalid API Key"}`. |
| OpenRouter: `https://openrouter.ai/api/v1`; `OPENROUTER_API_KEY` | [Public catalog](https://openrouter.ai/api/v1/models): observed 468 entries; 14 `:free`, 17 zero prompt/completion price. Not all are chat. [Free limits](https://openrouter.ai/docs/api-reference/limits): **20 RPM**, 50 RPD below $10 all-time purchased credits, 1000 RPD at/above $10. Daily cap unset because tier unknown. | Non-strict, upstream-dependent [privacy](https://openrouter.ai/docs/guides/privacy/data-collection). [OpenAI quickstart](https://openrouter.ai/docs/quickstart). `/models` **200**, no key. |
| SambaNova: `https://api.sambanova.ai/v1`; `SAMBANOVA_API_KEY` | [Free limits table](https://docs.sambanova.ai/docs/en/models/rate-limits): `DeepSeek-V3.1`, `DeepSeek-V3.2`, `Meta-Llama-3.3-70B-Instruct`, `gpt-oss-120b`, `gemma-4-31B-it`: **20 RPM / 20 RPD**. Prices unset except documented free tier. DeepSeek IDs absent from observed live list; only discovered IDs become routable. | Non-strict: [no-training claim](https://community.sambanova.ai/t/data-handling-and-retention/1314) is a community/support response, not contractual. [Plans](https://cloud.sambanova.ai/plans) says purchase credits to run first requests, conflicting with free limits table; verify entitlement. [Base URL](https://docs.sambanova.ai/docs/en/get-started/api-keys-urls.md). `/models` **200**, 5 models. |
| Cloudflare: `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1`; `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | Model IDs/prices unset. [Pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/): 10,000 free Neurons/day, then $0.011/1000 Neurons on Workers Paid. [Limits](https://developers.cloudflare.com/workers-ai/platform/limits/): non-paid text default **300 RPM**; paid model limits differ. | Strict eligible per [no training / retention policy](https://developers.cloudflare.com/workers-ai/platform/data-usage/). [Compatible URL format](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/). Placeholder-account `/ai/v1/models` **405**, not an account-auth check. Model discovery blocked, not guessed. |
| Nebius: `https://api.tokenfactory.nebius.com/v1`; `NEBIUS_API_KEY` | No fixed models, prices or limits. Live IDs and map prices are synced when a key is supplied. [Dynamic limits](https://docs.tokenfactory.nebius.com/ai-models-inference/rate-limits.md); no local RPM cap. | Non-strict until policy/account ZDR verified. [Legal guide](https://docs.tokenfactory.nebius.com/legal/legal-quick-guide) and [terms](https://docs.tokenfactory.nebius.com/legal/terms-of-service) differ on speculative-model training/applicability. Canonical [migration guide](https://docs.tokenfactory.nebius.com/other-capabilities/migration-guide), [compatibility](https://docs.tokenfactory.nebius.com/switch.md). Both hosts **401**, below. |

### Nebius migration evidence

[Migration guide](https://docs.tokenfactory.nebius.com/other-capabilities/migration-guide):
“We are announcing **Nebius Token Factory**, the next evolution of Nebius AI Studio”;
“Update your API end points to: **https://api.tokenfactory.nebius.com/v1**”.
The guide's old-key deadline is January 31, 2026 (already past); we do not assume
old keys work. Canonical documentation, not a responding old host, determines
the configured URL.

Unauthenticated observations on 2026-11-16:

```text
GET https://api.studio.nebius.com/v1/models -> 401
{"detail":"Couldn't authenticate. Reason: token is not present"}
GET https://api.tokenfactory.nebius.com/v1/models -> 401
{"detail":"Couldn't authenticate. Reason: token is not present"}
```

## Verification status / blocked

* **All providers:** authenticated inference, actual account model entitlement,
  billing tier/prices, remaining daily quota and settings are blocked: needs
  API key. Test MockTransport responses are confined to `tests/`; they do not
  establish real provider success.
* **Google:** compatible model-list path returned 404; native listing needs a
  key. Account-specific numeric RPM/RPD unset; free model eligibility is
  documented only for the recorded example, not every discovered model.
* **Groq:** 403 security response does not establish auth behavior; free limits
  and paid prices are public docs, not verified account billing. ZDR must be
  checked/enabled by the account owner.
* **NVIDIA:** fixed RPM/daily limits unset; hosted free-prototyping entitlement
  and privacy settings unverified. Trial policy excludes strict routing.
* **Mistral:** free-eligible models, prices and numeric limits unset. Models
  without verified free eligibility are not default-route candidates.
* **OpenRouter:** current purchase tier (50 vs 1000 RPD) and individual upstream
  privacy policies unknown. Zero price never establishes capabilities/privacy.
* **SambaNova:** formal current privacy guarantee and effective free entitlement
  unresolved; free documentation conflicts with plans page. Paid prices unset.
* **Cloudflare:** no real account probe; model IDs, model-specific prices and
  compatible model-discovery path/schema unverified. Discovery and therefore
  routing remain blocked even with keys until verified; no model is invented.
* **Nebius:** authenticated models/prices/limits and applicable privacy contract
  blocked; no fixed ID/price/quota is configured.
* A synchronized third-party price/capability entry is not authenticated proof.
  Unknowns stay null/unsupported. Missing keys and unsupported candidates are
  traceable errors, never simulated successful completions.

## CI

The Tokens with Taste job in `.github/workflows/ci.yml` installs this explicit
package and runs pytest on Python 3.11. Tests use `httpx.MockTransport` and ASGI
transport, with no external network or credentials.

### Strong routing profile

Send `model: "route:strong"` to prefer configured stronger models without
changing `default` or the local-only route. Configure the gateway process with
`TWT_STRONG_MODELS`, a JSON object mapping provider IDs to exact synced model IDs,
and `TWT_OLLAMA_STRONG_MODEL`, an installed local Ollama chat model. For example,
`TWT_STRONG_MODELS='{"nvidia":"your-synced-strong-model","nebius":"your-synced-strong-model"}'`.
Use actual catalog IDs, these placeholders are not model recommendations.
Run `twt sync` to validate/sync the local strong model alongside hosted catalogs.
Ollama must have cloud disabled. Do not combine this mixed-profile service with
`TWT_OLLAMA_MODEL`, which deliberately keeps the entire service local-only.

The strong profile tries local first, eligible free providers next, and Nebius
last. A provider without a strong selection keeps its ordinary model selection.
An unavailable selected strong model is skipped, never replaced with a weak
model at that provider. Existing privacy, capabilities, cooldowns, daily budget
and receipt accounting still apply. Set `TWT_DAILY_BUDGET_USD=5` for a $5 daily
cap, this profile does not change or bypass the configured budget.

Remote-server integration example, set in that repository's coder configuration
(see its `docs/twt-queue.md`): `CODER_STRONG_MODEL=route:strong`.
This source change does not modify a running host or register models remotely.
