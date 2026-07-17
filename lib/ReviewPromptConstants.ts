export const STRICT_JSON_VERIFICATION = `Strict JSON Verification:
- You MUST self-verify the completeness and validity of the JSON block before finishing your response.
- Every finding MUST have an \`id\`, \`file\`, \`issue\`, and \`status\`.
- Ensure the JSON is well-formed and contained entirely within the \`<findings>\` tags.
- Ensure 'snippet' is a unique string from the diff that identifies the issue.`;

export const SNIPPET_AND_VERIFICATION_RULES = `Snippet and verification rules:
- STRICT SNIPPET RULE: Quote the entire, exact line from the diff in the "snippet" field.
- Never assume a line truncated at the edge of a chunk is a syntax error; assume it is valid and continues outside.`;

export const COMMON_REVIEW_GUIDELINES = `Review ONLY PR changes. Assume original code worked.
EVIDENCE RULE: Issue must point to exact line + explain runtime consequence.
FALSE POSITIVE FILTER: No speculation. Design choices are NOT bugs.

TIERED SCOPE:
- For App/UI (src/): Flag redundant wrappers. BANNED: Raw Tailwind layout (flex/grid/px-*) in TSX (use Stack/Grid/Box).
- For Infra/Tooling (scripts/, cli/, .github/): Focus on portability, idempotency, and error handling. Avoid UI-specific feedback for low-level scripts.

REPO RULES: Prefer removal.
ANTI-SLOP: DO NOT recommend complex error handling, defensive guards, boilerplate comments, or complex nested directory scanning/redundant folder loops/non-standard directory checks in workflows/composite actions (keep paths direct and explicit).

- FILE NECESSITY: Question any added, moved, or removed files that look like temporary artifacts (e.g. .tmp, standalone .py in root, audit-*.md, .json dumps) or seem unrelated to the PR intent. Flag them for removal if they pollute the review context.`;

export const REVIEW_PHILOSOPHY = `## 1. Philosophy
- EVIDENCE RULE: Points to exact line + explain runtime consequence. No speculation.
- SCOPE: Review ONLY PR changes. Ignore pre-existing issues. Assume original code worked.
- STRICT SCOPE: Only review the lines present in the diff or the provided external context.
- FALSE POSITIVE FILTER: Verify if it occurs at runtime. Design choices are NOT bugs.
- DO NOT flag "missing" imports/types/files unless proven broken; assume correct definitions elsewhere. Do not hallucinate unseen bugs.
- Flag security issues ONLY if this diff introduces a NEW untrusted input path.
- Do not introduce review topics unrelated to the PR's stated goal.
- If parts of the diff/context are truncated ("[TRUNCATED]"), do not fail the review solely because of that; provide a WARN/PASS based on what is visible, stating what is unverified.
- CONFIGURATION EXEMPTION: Local workspace configuration and build files (e.g., \`.dependency-cruiser.config.mjs\`, \`project_config.json\`, \`.jscpd.json\`, or lint configs) are trusted and exempt from security policies. Do not speculate on hypothetical tampering or recommend integrity checksums/tampering verification for them.`;
