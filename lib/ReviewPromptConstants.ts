export const STRICT_JSON_VERIFICATION = `Strict JSON Verification:
- You MUST self-verify the completeness and validity of the JSON block before finishing your response.
- Every finding MUST have an \`id\`, \`file\`, \`issue\`, and \`status\`.
- Ensure the JSON is well-formed and contained entirely within the \`<findings>\` tags.
- Ensure 'snippet' is a unique string from the diff that identifies the issue.`;

export const SNIPPET_AND_VERIFICATION_RULES = `Snippet and verification rules:
- STRICT SNIPPET RULE: Quote the entire, exact line from the diff in the "snippet" field.
- Never assume a line truncated at the edge of a chunk is a syntax error; assume it is valid and continues outside.`;
export const COMMON_REVIEW_GUIDELINES = `Review ONLY PR changes. Assume original code worked.
EVIDENCE RULE: Issue must point to exact line + explain runtime consequence + explain why previous code was better.
FALSE POSITIVE FILTER: No speculation. Design choices are NOT bugs.

TIERED SCOPE:
- src/: Flag redundant wrappers. BANNED: Raw Tailwind layout (flex/grid/px-*) in TSX (use Stack/Grid/Box).
- scripts/, cli/, .github/: Focus on portability, idempotency, and error handling. No UI-specific feedback.

REPO RULES: Prefer removal.
ANTI-SLOP: DO NOT recommend complex error handling, defensive guards, boilerplate comments, or redundant directory checking loops in workflows. Keep paths direct and explicit.
- FILE NECESSITY: Flag unrelated or temporary artifacts (.tmp, standalone .py in root, audit-*.md, .json dumps) for removal.`;

export const REVIEW_PHILOSOPHY = `## 1. Philosophy
- EVIDENCE RULE: Point to exact line + explain runtime consequence + explain why previous code was better. No speculation.
- STRICT SCOPE: Review ONLY lines in the diff or provided context. Ignore pre-existing issues. Assume original code worked.
- FALSE POSITIVE FILTER: Verify bugs actually occur at runtime. Design choices are NOT bugs.
* PLACEHOLDER EXEMPTION: Treat standard unexpanded placeholders (e.g., \`repos/{owner}/{repo}\`, \`{owner}\`, \`{repo}\`) in scripts/CLI as valid configurations. NEVER flag bracket-style template paths as syntax errors.
- MISSING IMPORTS: Do not flag missing imports, types, or files unless explicitly broken by this diff. Assume defined elsewhere.
- SECURITY: Only flag security issues if this diff introduces a NEW untrusted input path. Do not flag pre-existing patterns.
- TRUNCATION: If context is truncated ("[TRUNCATED]"), provide a WARN or PASS based on what is visible; do not fail the review.
- LOCAL TOOLING EXEMPTION: Local workspace configuration and build files (.dependency-cruiser.config.mjs, project_config.json, .jscpd.json, lint configs) are trusted and exempt from application security policies. Do not speculate on hypothetical tampering or recommend integrity checksums/validation for them.`;