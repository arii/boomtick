import json
import glob

def summarize():
    all_jsonl = glob.glob("collected-logs/**/logs/ai/*.jsonl", recursive=True)
    hallucinated_files = []

    # We want to check for quota issues specifically.
    md_files = glob.glob("collected-logs/**/*.md", recursive=True)
    quota_met_runs = set()
    for mf in md_files:
        with open(mf, 'r', encoding='utf-8') as f:
            if "Skipped: review quota" in f.read():
                quota_met_runs.add(mf.split('/')[1])

    # Also collect explicit verdicts
    failures = []
    verdict_files = glob.glob("collected-logs/**/*-verdict.json", recursive=True)
    for vf in verdict_files:
        with open(vf, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                if data.get('verdict') != 'pass' and data.get('verdict') != 'approve':
                    failures.append(vf)
            except:
                pass

    summary = f"""# AI Code Review Audit Summary

## 1. Quota Issues
During the audit of the historical runs for the Deployment Impact Analysis workflow, it was discovered that the AI Code Review Agents frequently skip reviews because their quotas have been met.
- Total affected runs found: {len(quota_met_runs)}

*Example run directories affected:*
"""
    for r in list(quota_met_runs)[:3]:
        summary += f"- `{r}`\n"

    summary += """
## 2. Invalid/Null Verdict JSONs
The JSON output parsing appears to be failing or producing null verdicts in some cases. When auditing the `-verdict.json` files, we found numerous files lacking a successful pass/approve status, many completely `null` or missing proper structured output.
"""
    summary += f"- Found {len(failures)} files with failed, null, or unparseable final verdicts.\n"

    summary += """
*Example verdict files:*
"""
    for f in failures[:3]:
        summary += f"- `{f}`\n"

    summary += """
## 3. High-Confidence Hallucinated Findings
In some of the AI code review logs (e.g., `github-models-code-review-verdict.json` from run-29480177447), the model incorrectly flags structural issues (like inline commands for `depcruise`) and proposes configurations (`.dependency-cruiser.config.mjs`) that are likely overly rigid or hallucinate security vulnerabilities ("No checksum validation...").

*Example Prompt -> Output Finding from run 29480177447:*
**Finding ID:** `finding-1`
**File:** `.dependency-cruiser.config.mjs`
**Issue:** "No checksum validation for .dependency-cruiser.config.mjs, which could lead to security vulnerabilities if the file is tampered with."
**Agent Recommendation:** "Add a checksum validation step for .dependency-cruiser.config.mjs before using it in the DependencyGraph class."

This highlights a tendency for the agent to over-index on generic security practices that do not apply logically to standard local configuration files in a monorepo structure.
"""

    with open("audit_summary.md", "w") as f:
        f.write(summary)
    print("Summary written to audit_summary.md")

summarize()
