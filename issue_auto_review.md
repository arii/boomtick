# Enhance Auto-Review Agentic Workflows for CI/CD

# Problem Statement
The current automated review workflows (review-all-prs.md, review-pr.md) provide a basic structure for an agent to review code. However, they lack comprehensive instructions for providing actionable, inline feedback or leveraging multi-model review chains (like the dynamic code_review_chain and triage_chain defined in project_config.json) effectively to maximize review quality while minimizing costs.

# Goal
Enhance the existing .agents/workflows/review-pr.md and .agents/workflows/review-all-prs.md to formally integrate the multi-tiered model approach (Triage Agent -> Specialist Agent) and mandate inline actionable feedback formatting.

# Non-Goals
- Implementing new AI models or SDKs.
- Modifying the execution logic inside cli/dev_tools/.

# Proposed Approach
Update .agents/workflows/review-pr.md and .agents/workflows/review-all-prs.md to:
- Explain the fallback registries and dynamic code_review_chain / triage_chain configuration.
- Provide explicit instruction on when an agent should utilize a triage vs a specialist approach based on diff complexity.
- Define a standard formatting structure for inline feedback.

# Alternatives Considered
- Creating entirely new markdown files for multi-tier reviews. Rejected because it's better to improve the existing review instructions rather than fragmenting them.

# Architectural Impact
This aligns the agent markdown instructions with the already implemented GitHub Models client dynamic provider strategy capabilities. No code changes are required.

# Scope
Scope:
- Updating the review-pr.md and review-all-prs.md files in .agents/workflows/.

Affected Components and Files:
- .agents/workflows/review-pr.md
- .agents/workflows/review-all-prs.md

Dependencies and Sequencing:
- Depends on existing project_config.json definitions.

Risks and Edge Cases:
- Increased workflow token consumption if instructions are too verbose. We must keep instructions concise.

# UNDERSTAND THE ISSUE
The issue is about making the existing auto-review workflows more effective by documenting the usage of the existing tiered model architecture and enforcing better feedback formatting.

# DETERMINE APPROACH
Modify the existing .agents/workflows/review-pr.md and .agents/workflows/review-all-prs.md files to add the new requirements.

# SPECIFY SCOPE
Modify .agents/workflows/review-pr.md.
Modify .agents/workflows/review-all-prs.md.

# DEFINITION OF DONE
Acceptance Criteria:
- .agents/workflows/review-pr.md includes instructions for tiered models (Triage -> Specialist) and inline feedback formatting.
- .agents/workflows/review-all-prs.md includes instructions for tiered models (Triage -> Specialist) and inline feedback formatting.

Validation Steps:
- Run td-cli gh validate-issue --file issue_auto_review.md.
- Inspect the file content manually to ensure all acceptance criteria are met.
