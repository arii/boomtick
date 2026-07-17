export const STRICT_JSON_VERIFICATION = `Strict JSON Verification:
- You MUST self-verify the completeness and validity of the JSON block before finishing your response.
- Every finding MUST have an \`id\`, \`file\`, \`issue\`, and \`status\`.
- Ensure the JSON is well-formed and contained entirely within the \`<findings>\` tags.
- Ensure 'snippet' is a unique string from the diff that identifies the issue.`;

export const SNIPPET_AND_VERIFICATION_RULES = `Snippet and verification rules:
- STRICT SNIPPET RULE: When citing an error or anti-pattern, you MUST quote the entire, exact line from the diff in the "snippet" field. Do not truncate the line.
- Before flagging a "syntax error" or "missing property/method", re-read the diff to confirm the code isn't simply continued on the next line or truncated in the diff chunk. Hallucinating errors due to chunk truncation is a severe failure.
- If a line appears truncated in the diff (e.g. at the edge of a chunk), DO NOT assume it is a syntax error. Assume it is valid code that continues outside the visible context.`;

export const COMMON_REVIEW_GUIDELINES = `Review ONLY PR changes. Assume original code worked.
EVIDENCE RULE: Issue must point to exact line + explain runtime consequence.
FALSE POSITIVE FILTER: No speculation. Design choices are NOT bugs.

TIERED SCOPE:
- For App/UI (src/): Flag redundant wrappers. BANNED: Raw Tailwind layout (flex/grid/px-*) in TSX (use Stack/Grid/Box).
- For Infra/Tooling (scripts/, cli/, .github/): Focus on portability, idempotency, and error handling. Avoid UI-specific feedback for low-level scripts.

REPO RULES: Prefer removal.
ANTI-SLOP: DO NOT recommend overly complex error handling, defensive guards, extra unit tests for simple internal scripts, or boilerplate documentation/comments.
For workflows and composite actions, explicitly forbid recommending complex nested directory scanning, redundant folder loops, or non-standard directory checks (such as duplicate nested shell scanning patterns or abstract directory parsing overhead). Keeping YAML paths simple, direct, and explicit is required.

- FILE NECESSITY: Question any added, moved, or removed files that look like temporary artifacts (e.g. .tmp, standalone .py in root, audit-*.md, .json dumps) or seem unrelated to the PR intent. Flag them for removal if they pollute the review context.`;

export const REVIEW_PHILOSOPHY = `## 1. Philosophy
- EVIDENCE RULE: Points to exact line + explain runtime consequence + explain why previous code was better. No speculation.
- SCOPE: Review ONLY PR changes. Ignore pre-existing issues. Assume original code worked.
- STRICT SCOPE: Only review the lines present in the diff or the provided external context.
- FALSE POSITIVE FILTER: Verify if it occurs at runtime. Design choices are NOT bugs.
- DO NOT flag "missing" imports, types, or files unless you can prove they were deleted or broken by this diff. If a symbol is used but its definition is not in the context, ASSUME it is correctly defined elsewhere.
- DO NOT hallucinate bugs in code you cannot see.
- Flag security issues ONLY if this diff introduces a NEW untrusted input path (e.g. new user-controlled data flowing somewhere it wasn't before). Do not flag pre-existing patterns.
- Do not introduce review topics unrelated to the PR's stated goal unless you find a genuine, evidence-backed regression caused by this diff.
- If parts of the diff or external context are truncated (indicated by "[TRUNCATED]"), DO NOT fail the review solely because you cannot see the full implementation of a newly introduced module or utility. Instead, provide a WARN or PASS verdict based on what you CAN see, and explicitly state what remains unverified due to truncation.
- CONFIGURATION & LOCAL TOOLING EXEMPTION: Local configuration, infrastructure, and build-related files (e.g., \`.dependency-cruiser.config.mjs\`, \`project_config.json\`, \`.jscpd.json\`, or typescript/lint configs) are exempt from application security policies. Never flag local configuration files as having security vulnerabilities such as "missing checksum validation" or "susceptibility to tampering". Flagging local files for lack of cryptographic validation or tampering protection is a severe hallucination.
- NO TAMPERING OR INTEGRITY SPECULATION: Do not speculate about hypothetical attacker modifications to local workspace configuration files. Local config files are trusted by definition at build/runtime. Recommendation of integrity checksum validation or runtime signatures for standard workspace config files is strictly prohibited.`;
