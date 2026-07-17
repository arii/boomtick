# Draft: Implement E2E validation for impact analysis CI Metrics
## Problem Statement
The CI metrics verification script (`cli/dev_tools/utils/__init__.py:verify_ci_metrics`) expects specific token thresholds to enforce usage limits during pull request impact analysis workflows. While there is test coverage for CI metrics in `cli/tests/test_verify_ci_metrics.py`, we must ensure comprehensive end-to-end testing to verify the entire toolchain properly integrates into GitHub workflows, particularly `mcp/actions/impact-analysis`.

## Goal
Implement end-to-end validation tasks for the impact analysis tool suite, focusing on the correct reporting, parsing, and failure behaviors of AI token thresholds within CI metrics.

## Non-Goals
*   We will not modify the underlying token thresholds.
*   We will not implement new tools; we will verify the existing ones.
*   We will not modify the dependency cruiser configurations or TS code in `scripts/`.

## Proposed Approach
1.  Review and document the current end-to-end behavior of the CI token limits in `.github/workflows/ci.yml`.
2.  Enhance the `verify_ci_metrics` tests in `cli/tests/test_verify_ci_metrics.py` to cover cases where token usage exceeds the configured environment variables (`MAX_INPUT_TOKENS`, `MAX_OUTPUT_TOKENS`, `MAX_TOTAL_TOKENS`).
3.  Write tests in `cli/tests/test_verify_ci_metrics.py` to verify the fallback logic when token usage logs are missing, ensuring they don't incorrectly fail CI builds that skip visual or code reviews.

## Alternatives Considered
*   Relying solely on manual testing during pull requests. This is error-prone and doesn't ensure long-term stability for consumer repositories using the composite action.
*   Integrating tests directly into the `impact-analysis` TypeScript scripts instead of Python. However, the CI metric verification happens in Python, so the tests belong in the CLI's Python test suite.

## Architectural Impact
Minimal. This will add test cases to the existing test suite (`cli/tests/`) and improve the reliability of the Boomtick template for consumers.

## Scope
*   `cli/dev_tools/utils/__init__.py` (only if minor fixes are needed for env var handling)
*   `cli/tests/test_verify_ci_metrics.py`

## UNDERSTAND THE ISSUE
The current impact analysis utilizes LLM agents for code and visual reviews. These can consume significant tokens. To protect the API quotas, token thresholds are enforced by `verify_ci_metrics`. Testing this verification logic end-to-end is critical to avoid false positives and false negatives in CI.

## DETERMINE APPROACH
The logic is already implemented in `cli/dev_tools/utils/__init__.py`. We will focus on enhancing the existing tests in `cli/tests/test_verify_ci_metrics.py` to mock `os.environ` to simulate different threshold configurations and token usage outcomes.

## SPECIFY SCOPE
*   `cli/tests/test_verify_ci_metrics.py`: Add test cases for various threshold breach conditions.

## DEFINITION OF DONE
*   Unit tests cover cases where token thresholds are exceeded.
*   Unit tests cover cases where token thresholds are overridden by environment variables.
*   All tests pass successfully (`pnpm run test` and `pytest cli/tests`).
