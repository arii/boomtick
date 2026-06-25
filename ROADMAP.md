# BoomTick: AI-Enabled Workspace Roadmap

Bootstrap spec for a self-healing, self-improving repo skeleton. Start simple.
Everything outputs JSON. Complexity is added only when the current approach
breaks.

---

## Invariants

- All business logic lives in `dev-tools`. MCP and CI are thin clients.
- The orchestrator is the only workflow that dispatches agents.
- No agent may modify workflow files, Dockerfile, or `.devcontainer/`.
- Only `ai-improve` may propose changes to `audit.config.yaml` or `AGENTS.md`, via PR.
- Same fix, same file, 3x failures → escalate to human, stop retrying.

---

## File Tree

```
.agent/
  AGENTS.md
  audit.config.yaml
  orchestration.config.yaml

.devcontainer/
  Dockerfile
  devcontainer.json

.github/
  workflows/
    publish-runner.yml
    ci-validate.yml
    ai-orchestrator.yml
    ai-heal.yml
    ai-improve.yml
  actions/
    setup-workspace/
      action.yml

ai-reports/
  .gitkeep

boomtick-mcp/
  src/
    index.ts
    lib/shell.ts
    tools/
      index_workspace.ts
      score_workspace.ts
      suggest_tools.ts
  package.json
  tsconfig.json

dev-tools/
  dev_tools_sdk/
    __init__.py
    indexer.py
    audit_scorer.py
    triage.py
    fix_prompt_builder.py
    pattern_analyzer.py
    tool_suggester.py
    orchestrator/
      task_queue.py
      run_history.py
      escalation.py
      lock_manager.py
  runners/
    run_validate.py
    run_heal.py
    run_improve.py
    run_orchestrate.py
  pyproject.toml

src/
setup-agent.sh
```

---

## Section 1: Dev Environment

- [ ] `Dockerfile` — Node 20, pnpm, Python 3.11; pre-install `dev-tools` in
      editable mode so `td-*` entry points work without a setup step
- [ ] `devcontainer.json` — single source of truth for Node and Python versions
- [ ] `setup-agent.sh` — one command: install dev-tools + build boomtick-mcp
- [ ] `publish-runner.yml` — rebuild and push image to GHCR when
      `.devcontainer/`, `dev-tools/`, or `boomtick-mcp/` changes

---

## Section 2: dev-tools SDK

All modules output JSON to stdout. Start with the simplest implementation that
works. Add complexity only when output proves insufficient.

- [ ] `indexer.py` — file inventory of workspace
- [ ] `audit_scorer.py` — score files against `audit.config.yaml` rules
- [ ] `triage.py` — classify failure as `fixable` or `needs-comment`
- [ ] `fix_prompt_builder.py` — build LLM prompt from audit result + file
      content; no RAG until flat file context proves insufficient
- [ ] `pattern_analyzer.py` — read `ai-reports/` and surface repeated failures;
      starts silent, produces signal after first few runs
- [ ] `tool_suggester.py` — read pattern output, suggest new MCP tools
- [ ] `orchestrator/task_queue.py` — Task, TaskStatus, TaskQueue
- [ ] `orchestrator/run_history.py` — read/write `ai-reports/` JSON files
- [ ] `orchestrator/escalation.py` — open GitHub issue when loop detected
- [ ] `orchestrator/lock_manager.py` — flat file locks with TTL
- [ ] `runners/` — one file per workflow; calls SDK, writes JSON artifact,
      nothing else

**`pyproject.toml` entry points:**
```
td-index   → indexer:main
td-score   → audit_scorer:main
td-triage  → triage:main
td-suggest → tool_suggester:main
```

---

## Section 3: MCP Gateway

- [ ] `lib/shell.ts` — `execFile` only, positional args, 30s timeout
- [ ] `tools/index_workspace.ts` — runs `td-index`, returns JSON to LLM
- [ ] `tools/score_workspace.ts` — runs `td-score`, returns JSON to LLM
- [ ] `tools/suggest_tools.ts` — runs `td-suggest`, returns JSON to LLM
- [ ] Register in Claude Desktop and agent session configs

---

## Section 4: Agent Config

- [ ] `AGENTS.md` — architecture rules, import boundaries, banned vocabulary
- [ ] `audit.config.yaml` — scoring rules and weights, `llm_budget` per agent
- [ ] `orchestration.config.yaml` — retry limits, score thresholds, restricted
      files per agent, loop detection window, lock TTL

---

## Section 5: CI/CD Pipeline

- [ ] `ci-validate.yml` — score workspace, upload `validate-result.json`,
      trigger orchestrator on failure
- [ ] `ai-orchestrator.yml` — read result, check history and locks, dispatch
      heal or improve, write outcome to `ai-reports/`
- [ ] `ai-heal.yml` — fixable → PR on `ai/fix-{run-id}` requiring approval;
      non-fixable → diagnosis comment on PR
- [ ] `ai-improve.yml` — weekly + manual; Job A: evolve audit config from
      history; Job B: refactor low-scoring files; Job C: commit tool suggestions
      to `ai-reports/`
- [ ] `setup-workspace/action.yml` — shared bootstrap composite action

---

## Bootstrap Sequence

```
1.  Dockerfile + devcontainer.json + setup-agent.sh
2.  dev-tools core: indexer, audit_scorer, triage, fix_prompt_builder
3.  pyproject.toml entry points — verify td-* commands run
4.  audit.config.yaml + orchestration.config.yaml (minimal)
5.  ci-validate.yml + setup-workspace action
6.  boomtick-mcp: shell.ts + index_workspace tool
7.  orchestrator: task_queue, run_history, lock_manager, escalation
8.  ai-orchestrator.yml + ai-heal.yml
9.  pattern_analyzer + tool_suggester + ai-improve.yml
10. AGENTS.md + per-agent session files
11. publish-runner.yml
```

## Toolkit Enhancements
- `search_issue.py`: A utility script created to quickly query DuckDuckGo via CLI using Python. Useful for debugging CI/CD generic failure patterns (like GHCR manifest unknown errors). Can be added to `dev-tools` as a standard utility for agents diagnosing issues.

```python
import urllib.request
import urllib.parse
import sys

def search_duckduckgo(query):
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
        print(html[:2000])
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        search_duckduckgo(" ".join(sys.argv[1:]))
    else:
        print("Usage: python search_issue.py <query>")
```
