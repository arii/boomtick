# Comprehensive PR Review (All PRs)

Please perform a comprehensive technical review of all currently open pull requests using our multi-tiered agentic review workflow.

## 1. Multi-Tiered Model Configuration & Fallbacks
The review system leverages a dynamic, resilient provider strategy configured in `project_config.json`:
- **triage_chain**: Configured for initial triage.
  - *Primary*: `gpt-4o-mini` (or env override `AI_TRIAGE_CHAIN_PRIMARY`).
  - *Fallbacks*: `llama-3.3-70b-instruct` (or env override `AI_TRIAGE_CHAIN_FALLBACKS`).
- **code_review_chain**: Configured for deep, specialized review.
  - *Primary*: `gpt-4o` (or env override `AI_SPECIALIST_CHAIN_PRIMARY`).
  - *Fallbacks*: `deepseek-r1`, `llama-3.3-70b-instruct` (or env override `AI_SPECIALIST_CHAIN_FALLBACKS`).

**Fallback Registry Mechanism:**
In case of recoverable errors (429 rate limits, 50x server errors), the client automatically retries with exponential backoff and cascades through the defined fallback models. This ensures zero-disruption execution even during API degradation.

## 2. Triage vs. Specialist Review Decision
Review execution must utilize the multi-tiered model pipeline based on diff complexity to optimize cost and quality:
- **Triage Phase (Triage Agent)**:
  - Validates the diff context initially.
  - **Triage Decision**:
    - *Simple Changes*: Small style cleanups, documentation, small utility functions, configuration tweaks, or minor text modifications are handled directly in the triage phase using fast/cheap models.
    - *Complex Changes*: Architectural adjustments, core layout/UI additions, data flow changes, performance-sensitive algorithms, or potential security implications are flagged to trigger the specialist phase.
- **Specialist Phase (Specialist Agent)**:
  - Triggered automatically when triage detects complexity. Executes deep, isolated analysis with a high-capacity model (e.g., `gpt-4o` / `deepseek-r1`) to find edge cases and vulnerabilities.

## 3. Standard Inline Feedback Formatting
To ensure clarity, usefulness, and easy parsing, all inline comments provided in the review metadata JSON must adhere strictly to the following markdown structure inside the comment body:

```markdown
### `[Category]` **[Brief Summary]**
- **Issue**: Clear and objective explanation of the problem, referencing specific lines/variables. Avoid speculative language.
- **Actionable Fix**: Concrete code correction or exact step to resolve the issue. Provide inline code snippets where possible.
```

*Allowed Categories*: `Logic`, `Security`, `Performance`, `Consistency`, `Quality`.

## 4. Evaluation Criteria
For each pull request, evaluate the following:
1. **Logic Errors & Bugs**: Check for logic flaws, incorrect assumptions, or unhandled edge cases.
2. **Security Vulnerabilities**: Identify any security risks, unsanitized inputs, or dangerous patterns.
3. **Performance Issues**: Look for unoptimized operations, missing limits, or memory leaks.
4. **Architectural Consistency**: Ensure the changes align with the existing system architecture and patterns.
5. **Code Quality**: Check code style, maintainability, readability, and documentation.

Provide a structured summary of your findings for each PR reviewed, highlighting any blocking issues or recommended improvements.
