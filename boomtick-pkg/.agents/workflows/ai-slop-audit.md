> Follow `.agents/AGENT_CONTRACT.md` before reading anything else.

# AI Slop Audit Workflow

This workflow does not hardcode violation examples. Reports are generated from `.agents/audit.config.yaml` at runtime by `.agents/scripts/audit-ai-slop.py`.

## Run

```bash
python3 .agents/scripts/audit-ai-slop.py
```

Use the generated report file in `.agents/workflows/` for current findings and action planning.
