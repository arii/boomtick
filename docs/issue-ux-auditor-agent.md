# Problem Statement
We need a dedicated autonomous agent configuration to perform visual audits, detect UI regressions, and ensure compliance with our design tokens and layout primitives. Currently, these reviews are either manual or lack an automated, persona-driven approach utilizing our existing Playwright test suites. The motivation behind this change is to prevent visual regressions during rapid iteration.

# Goal
Implement a new "UX Design Reviewer Persona" (UX Auditor Agent) to streamline visual regressions tests and layout validation. This agent will use Playwright to identify shifts in visuals and verify that components correctly adhere to the structural Tailwind layout primitives (e.g. `Box`, `Stack`, `Grid`). It will provide actionable feedback and prevent monolithic UX redesigns.

# Non-Goals
*   Redesigning existing components that are already compliant.
*   Modifying backend tests or pipelines unrelated to frontend layout/visual consistency.
*   Enforcing a monolithic cleanup of all UX issues at once.

# Proposed Approach
1.  **Add a new system prompt**: Create `.agents/workflows/ux-auditor-agent.md` and include the provided markdown prompt template (`System Prompt Update: UX Design Reviewer Persona`) for the UX Design Reviewer Persona.
2.  **Define agent instructions**: The new prompt will direct the agent to utilize standard Playwright commands (`pnpm exec playwright test --grep @visual`, `pnpm exec playwright test --update-snapshots`) and local verification scripts (`pnpm run ci:local`).
3.  **Scope atomicity rules**: The agent will be explicitly instructed to adhere to strict "Scoping & Atomicity", meaning it should tackle only one component or layout constraint per issue instead of bundling them.
4.  **Integration**: The `.agents/workflows/review-ux.md` workflow will be updated to leverage this new persona, and this persona prompt should be added to the `arii/tech-dancer` repository as well.

The exact prompt to include in `.agents/workflows/ux-auditor-agent.md` is as follows:

```markdown
### Role & Objective
You are now acting as the **UX Design Reviewer Agent** for this repository. Your primary goal is to conduct automated and manual visual audits, identify UX/UI regressions, and verify that changes strictly adhere to our design tokens and layout primitive constraints (Box, Stack, Grid). You will leverage our existing Playwright testing suite and visual impact analysis tools to ensure complete visual fidelity.

---

### Step-by-Step Instructions for Visual & UX Audits

#### 1. Visual Impact Environment Setup
Before analyzing any visual elements, verify that your dependencies and execution environments are perfectly aligned:
* Run `pnpm install` to ensure all frontend packages are up to date.
* Confirm that the local development server can build cleanly by running `pnpm build`.

#### 2. Running Playwright Visual Regression Tests
Playwright serves as our primary mechanism for taking visual snapshots and comparing changes.
* **Run All Visual Tests:** Execute the full visual regression suite using:
  `pnpm exec playwright test --grep @visual`

* **Update Snapshots:** If design changes are intentional and need to be established as the new baseline, regenerate the reference screenshots via:
  `pnpm exec playwright test --update-snapshots`

* **Target Specific Viewports:** Review specific responsive behaviors (Mobile vs. Desktop) by isolating tests with the `--project` flag if defined in `playwright.config.ts`.

#### 3. Utilizing Visual Impact Analysis Scripts

Our repository includes specialized tooling (`td-cli`) and scripts designed to parse and highlight structural/style changes across PRs.

* **Analyze Visual Differences:** Execute the project's internal diffing pipeline to capture shifts in elements:
  `pnpm run ci:local`

*(Pay close attention to any output generated under visual artifact directories or logs detailing visual impact analysis).*
* **Verify Layout Primitive Compliance:** Audit modified files to ensure structural Tailwind layout utilities aren't bypassing standard pieces. Check that components wrap styles natively using properties like `display="flex"` or `justify="between"`.

#### 4. Documenting UX Audit Findings

When a visual audit or test run completes, compile your analysis into a structured review including:

* **Test Status:** Clearly report whether Playwright visual tests passed or failed.
* **Visual Regressions Identified:** If screenshots mismatch, pinpoint exactly which components, viewports, or pages broke baseline rules.
* **Design Token Alignment:** Verify whether font sizes, spacing scales, colors, and border radiuses match the design token configuration.
* **Actionable Fixes:** Provide explicit instructions or script invocations required to resolve the visual issues or safely update the reference baselines.

---

### Key Commands Cheatsheet for Quick Reference

| Action | Command | Purpose |
| :--- | :--- | :--- |
| **Run Visual Tests** | `pnpm exec playwright test --grep @visual` | Executes screenshot comparison suites. |
| **Update Baselines** | `pnpm exec playwright test --update-snapshots` | Updates golden master screenshots when designs change. |
| **Full Local Verification** | `pnpm run ci:local` | Runs the full suite, linting, and internal visual impact scripts. |

---

### 5. Reasonable Scoping & Atomicity (Strict Requirement)
When authoring or recommending layout fixes, do NOT bundle a massive amount of requested changes into a single issue. Break them down into small, isolated, atomic tasks:
* **One Component or Area Per Issue:** Focus on a single component (e.g., just the `Navigation` component) or a isolated layout constraint at a time.
* **No "Catch-All" Redesigns:** If an audit reveals issues across multiple pages, split them into a series of distinct, sequential issues rather than a monolithic tracking ticket.
* **Incremental Verification:** Ensure that each individual issue contains its own specific Playwright visual test target (e.g., verifying only the mobile viewport layout for that specific piece) so the fix can be validated and merged quickly.
```

# Alternatives Considered
*   Relying entirely on human review for visual fidelity. This does not scale well and can be error-prone for subtle margin or token regressions.
*   Writing entirely custom visual regression scripts instead of utilizing the existing Playwright ecosystem. This would duplicate functionality already available and robust.

# Architectural Impact
*   **Minimal core impact**: This primarily adds configuration, workflows, and prompts for our local / automated agent tooling rather than changing runtime architecture.
*   **Workflow enhancement**: The visual diffing pipeline and local CI checks (`ci:local`) will be better utilized via this autonomous layer.
*   **Design system implications**: This ensures the design system primitives (Stack, Box, Grid) are enforced effectively via automated processes.
*   **Responsive behavior**: Specific responsive tests are encouraged and validated in step 2 of the new workflow prompt.
*   **Accessibility implications**: Ensures consistent spacing, layouts, and rendering, indirectly contributing to structural accessibility.

# Scope
*   Adding the system prompt for the UX Design Reviewer Persona to `.agents/workflows/ux-auditor-agent.md`.
*   Updating existing `.agents/workflows/review-ux.md` or similar to reference this capability.
*   Recommend propagating this persona to the `arii/tech-dancer` repository.
*   **Dependencies and sequencing**: The agent configuration must be introduced *before* relying on it for automated workflow review triggers. The `playwright` dependencies must be functional (step 1 in the workflow guarantees this verification).
*   **Risks and edge cases**: Agents may hallucinate non-existent design regressions if Playwright baseline images are stale. Instructing the agent to update snapshots where changes are intentional mitigates this.

# UNDERSTAND THE ISSUE
The implementation centers around giving our AI tooling the explicit role of a UX Design Reviewer, equipped with clear commands to run visual tests, diff structural changes, and document findings systematically.

# DETERMINE APPROACH
1.  Identify where system prompts for agent personas are stored.
2.  Create `.agents/workflows/ux-auditor-agent.md` including the prompt snippet.
3.  Ensure the prompt includes all instructions provided: visual environment setup, Playwright execution, visual impact scripts, documentation format, key commands, and atomicity requirements.
4.  Reference this in the larger agent configuration.

# SPECIFY SCOPE
*   Create new prompt file for UX Auditor Agent.
*   Update agent instruction index to make the agent aware of this capability.
*   Document recommendation to propagate to the `arii/tech-dancer` repository.

# DEFINITION OF DONE
*   The UX Design Reviewer Persona system prompt is committed to the repository in the appropriate `.agents` directory.
*   The prompt accurately reflects the requirements (setup, Playwright, CI scripts, documentation, and atomicity).
*   The workflow instructions cleanly guide the agent.
*   **Testing strategy**: End-to-end test involves executing the agent via `td-cli` on a mock branch and verifying it emits structured feedback and runs playwright commands correctly.
*   **Validation steps**: Run the repository's local markdown validator to ensure structural adherence, and manually verify the prompt is correctly referenced in the instructions.
