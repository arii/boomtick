# Problem Statement
Our current AI agent architecture relies heavily on single-model dependencies. This hardcoded approach makes our CI pipelines and review workflows brittle and highly susceptible to vendor outages and API rate limits (e.g., HTTP 429 or 5xx errors). We need a resilient architecture that gracefully handles these failures.

# Goal
Transition to a resilient, multi-model architecture by implementing a **Provider Strategy** pattern. This will separate business logic from specific model calls, allowing for automatic failover, environment-based model routing, and a tiered model approach to balance cost and capability.

# Non-Goals
*   Rewriting the actual AI review prompts or system instructions.
*   Building a custom, fully-fledged third-party AI proxy service (we will use an internal Adapter/Gateway layer).
*   Deploying models locally.

# Proposed Approach
1.  **Architectural Strategy (The Provider Boundary):**
    *   Create a single interface (e.g., `generateReview`) that accepts an intent instead of a hardcoded model ID.
    *   Treat the model list as dynamic configuration (e.g., environment variable or JSON config) rather than constants.
    *   Define an ordered `FallbackChain` (e.g., `primary: gpt-4o`, `fallbacks: [deepseek-r1, llama-3.3-70b]`).
2.  **Implementation in CI:**
    *   Update `codeReviewOrchestrator.ts` or `githubModelsCodeReviewClient.ts` to use a standardized model interface.
    *   Implement a "Circuit Breaker" with exponential backoff for rate limits.
    *   Differentiate between Recoverable Errors (429, 503) and Hard Failures (400, 401), only triggering fallbacks for the former.
    *   Add logging to track which model ultimately served the request.
3.  **Workflow Decomposition (Tiered Model Approach):**
    *   **Triage Agent:** Fast/cheap initial validation using models like `gpt-4o-mini` or `llama-3.3-70b`.
    *   **Specialist Agent:** Complex architectural issues handed off to `gpt-4o` or `deepseek-r1`.
    *   **Isolation:** Prevent bias by passing only the diff and requirements to the Specialist, omitting the Triage agent's reasoning.

# Alternatives Considered
*   Relying on single providers and implementing extensive manual retry logic. This does not protect against prolonged vendor outages.
*   Using third-party gateway services, which introduces an external operational dependency, whereas an internal Adapter layer is sufficient for our fallback needs.

# Architectural Impact
*   **Adapter Layer:** Introduces a centralized AI Gateway or Adapter pattern.
*   **Configuration:** Moves from hardcoded constants to runtime environment configurations (e.g., `code-review-chain` config).
*   **Error Handling:** Centralizes rate-limit handling and exponential backoff strategies into the orchestrator.
*   **Dependencies and sequencing:** The standardized interface must be implemented *before* the Circuit Breaker logic and fallback chain can be integrated into the orchestrator.
*   **Risks and edge cases:** Fallback models might produce lower-quality outputs or differently formatted responses. The standardized interface must strictly enforce expected JSON schemas regardless of the model backend.
*   **Accessibility implications:** No direct frontend visual accessibility impact, but ensures automated reviewers remain highly available to audit code.

# Scope
*   Extract and remove hardcoded model IDs from script handlers.
*   Create a model-agnostic `complete` function accepting a `ModelChain`.
*   Implement try-catch blocks handling `429` codes and automatic rotation.
*   Implement the configuration-driven fallback chain structure.

# UNDERSTAND THE ISSUE
The objective is to eliminate hardcoded model strings in favor of a dynamic `Provider Strategy`. If a GitHub Model like `gpt-4o` goes down or rate limits us, the orchestrator should automatically catch the `429/50x` error, back off, and seamlessly failover to a fallback like `deepseek-r1` or `llama-3.3-70b-instruct`. We will also utilize the available GitHub Models cost/multiplier metrics to strategically configure primary vs. fallback choices.

# DETERMINE APPROACH
1.  Refactor `codeReviewOrchestrator.ts` and `githubModelsCodeReviewClient.ts`.
2.  Define the `FallbackChain` interface and JSON config structure.
3.  Implement the exponential backoff and error classification logic.
4.  Update logging mechanisms to record the invoked model.
5.  Reference the GitHub Models cost structure to set default chains:
    *   *Triage:* `gpt-4o-mini` ($0.15/$0.60 per 1M) or `Llama-3.3-70B-Instruct` ($0.71 per 1M).
    *   *Specialist:* `gpt-4o` ($2.50/$10.00 per 1M) or `DeepSeek-R1` ($1.35/$5.40 per 1M).

# SPECIFY SCOPE
*   Update `ci.yml` or global config to define model chains.
*   Implement `generateReview` unified interface.
*   Implement Tiered Model Triage -> Specialist routing.

# DEFINITION OF DONE
*   Hardcoded model IDs are completely removed from execution paths.
*   A `ModelChain` config is successfully parsed and utilized during CI.
*   Simulating a 429 error automatically triggers the fallback model.
*   **Testing strategy:** Execute the existing test suite against both primary and fallback models to ensure logic consistency. Add a unit test that mocks a 429 response and asserts that the `fallback` model is successfully invoked.
*   **Validation steps:** Code reviews must confirm that vendor-specific logic does not leak into the core orchestration layer.

---

### Reference: Costs and multipliers for direct use of GitHub Models
*(For configuration reference when setting up the fallback chain)*

| Model name                        | Input multiplier | Cached input multiplier | Output multiplier | Input price (per 1M token units) | Cached input price (per 1M token units) | Output price (per 1M token units) |
| --------------------------------- | ---------------- | ----------------------- | ----------------- | -------------------------------- | --------------------------------------- | --------------------------------- |
| OpenAI GPT-4o                     | 0.25             | 0.125                   | 1.0               | $2.50                            | $1.25                                   | $10.00                            |
| OpenAI GPT-4o mini                | 0.015            | 0.0075                  | 0.06              | $0.15                            | $0.08                                   | $0.60                             |
| OpenAI GPT-4.1-mini               | 0.04             | 0.01                    | 0.16              | $0.40                            | $0.10                                   | $1.60                             |
| OpenAI GPT-4.1                    | 0.2              | 0.05                    | 0.8               | $2.00                            | $0.50                                   | $8.00                             |
| Phi-4                             | 0.0125           | N/A                     | 0.05              | $0.13                            | N/A                                     | $0.50                             |
| Phi-4-mini-instruct               | 0.0075           | N/A                     | 0.03              | $0.08                            | N/A                                     | $0.30                             |
| Phi-4-multimodal-instruct         | 0.008            | N/A                     | 0.032             | $0.08                            | N/A                                     | $0.32                             |
| DeepSeek-R1                       | 0.135            | N/A                     | 0.54              | $1.35                            | N/A                                     | $5.40                             |
| DeepSeek-R1-0528                  | 0.135            | N/A                     | 0.54              | $1.35                            | N/A                                     | $5.40                             |
| DeepSeek-V3-0324                  | 0.114            | N/A                     | 0.456             | $1.14                            | N/A                                     | $4.56                             |
| MAI-DS-R1                         | 0.135            | N/A                     | 0.54              | $1.35                            | N/A                                     | $5.40                             |
| Grok 3 Mini                       | 0.025            | N/A                     | 0.127             | $0.25                            | N/A                                     | $1.27                             |
| Grok 3                            | 0.3              | N/A                     | 1.5               | $3.00                            | N/A                                     | $15.00                            |
| Llama 4 Maverick 17B Instruct FP8 | 0.025            | N/A                     | 0.1               | $0.25                            | N/A                                     | $1.00                             |
| Llama-3.3-70B-Instruct            | 0.071            | N/A                     | 0.071             | $0.71                            | N/A                                     | $0.71                             |
