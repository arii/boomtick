export const STRICT_JSON_VERIFICATION = `Strict JSON Verification:
- You MUST self-verify the completeness and validity of the JSON block before finishing your response.
- Every finding MUST have an \`id\`, \`file\`, \`issue\`, and \`status\`.
- Ensure the JSON is well-formed and contained entirely within the \`<findings>\` tags.
- Ensure 'snippet' is a unique string from the diff that identifies the issue.`;

export const SNIPPET_AND_VERIFICATION_RULES = `Snippet and verification rules:
- STRICT SNIPPET RULE: Quote the entire, exact line from the diff in the "snippet" field.
- Never assume a line truncated at the edge of a chunk is a syntax error; assume it is valid and continues outside.`;

export const REVIEW_PHILOSOPHY = `## 1. Philosophy
- EVIDENCE RULE: A blocking concern must point to a concrete contradiction in the diff itself (e.g. wrong type, nonexistent function/class, wrong arity, or failing test). Cite exact lines + explain runtime consequence + explain why previous code was better. No speculation.
- STRICT SCOPE: Review ONLY lines in the diff or provided context. Ignore pre-existing issues. Assume original code worked. Instruct reviewers to flag any unrequested file modifications (files modified that are not explicitly mentioned in the original problem statement or closely linked source/test files) as blocking review issues.
- FALSE POSITIVE FILTER: Verify bugs actually occur at runtime. Design choices are NOT bugs. No speculation. Concerns phrased with speculative hedging language (e.g., "could", "might", "unless", "if not handled properly") are NOT blocking.
* PLACEHOLDER EXEMPTION: Treat standard unexpanded placeholders (e.g., \`repos/{owner}/{repo}\`, \`{owner}\`, \`{repo}\`) in scripts/CLI as valid configurations. NEVER flag bracket-style template paths as syntax errors.
- MISSING IMPORTS: Do not flag missing imports, types, or files unless explicitly broken by this diff. Assume defined elsewhere.
- SECURITY: Only flag security issues if this diff introduces a NEW untrusted input path. Do not flag pre-existing patterns.
- TRUNCATION: If context is truncated ("[TRUNCATED]"), provide a WARN or PASS based on what is visible; do not fail the review.
- LOCAL TOOLING EXEMPTION: Local workspace configuration and build files (.dependency-cruiser.config.mjs, project_config.json, .jscpd.json, lint configs) are trusted and exempt from application security policies. Do not speculate on hypothetical tampering or recommend integrity checksums/validation for them.`;