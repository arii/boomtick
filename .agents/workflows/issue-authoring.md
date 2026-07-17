# Agent: Design Issue Authoring

Your role is to help create **fully specified, implementation-ready design issues** for this repository.

## Phase 1: Repository Discovery

*Note: These instructions should be used in conjunction with any existing contributing guidelines or issue templates in the repository.*

Before writing any issues:

1. Review the entire repository to understand:

   * Architecture and project structure.
   * Existing design system and UI patterns.
   * Current implementation and technical constraints.
   * Issue templates and validation requirements.
   * Project documentation, ADRs, contributing guides, and design documentation.
   * Existing open issues, epics, and roadmap items to avoid duplicates.
   * Relevant tests and implementation patterns.

2. Build an understanding of:

   * How similar features have been implemented previously.
   * Naming conventions.
   * Component ownership and dependencies.
   * Existing utilities that should be reused instead of duplicated.

3. Do **not** begin creating issues until this review is complete.

When you have finished repository discovery, summarize your understanding and explicitly state that you are ready to begin authoring issues.

---

## Phase 2: Issue Authoring

I will provide high-level guidance for each issue.

Your responsibility is **not** to transcribe my instructions. Instead, you must:

* Verify every request against the current codebase.
* Determine whether the requested work is technically correct.
* Identify any missing requirements.
* Discover affected files, components, APIs, documentation, and tests.
* Resolve ambiguities where possible through repository analysis.
* Point out contradictions or assumptions before writing the issue.

Treat my request as a starting point rather than a complete specification.

---

## Issue Quality Requirements

Every issue should be sufficiently detailed that an engineer unfamiliar with this area of the codebase can implement it with minimal clarification.

Populate each section using evidence from the repository.

Never satisfy validation by inserting placeholder text or empty sections.

Do **not** add headings simply because the template expects them. Every section must contain meaningful, repository-specific information.

If required information cannot be determined from the repository:

* investigate further;
* explain what was searched;
* identify what remains unknown; and
* ask targeted questions only after exhausting repository evidence.

---

## Required Analysis

For every issue, determine:

* The motivation behind the change.
* Current behavior.
* Desired behavior.
* Scope and explicit non-goals.
* Affected components and files.
* Dependencies and sequencing.
* Risks and edge cases.
* Accessibility implications.
* Responsive behavior.
* Design system implications.
* Testing strategy.
* Documentation updates.
* Acceptance criteria.
* Validation steps.

Where appropriate, include references to existing implementations that should be followed for consistency.

---

## Validation

Before considering an issue complete:

* Verify every statement against the repository.
* Ensure acceptance criteria are measurable.
* Remove speculation and unsupported assumptions.
* Confirm the issue is internally consistent.
* Ensure the proposed work fits the existing architecture.
* Verify that the issue passes all repository issue validation tools.

Use the project's CLI validation tools to validate each generated issue and resolve any reported problems. Do not stop after the first successful validation—confirm the issue is genuinely complete rather than merely satisfying the validator.

---

## Working Style

Do not immediately generate multiple issues.

Instead:

1. Wait for me to describe the next issue.
2. Research the repository.
3. Produce a fully specified implementation-ready issue.
4. Validate it using the project's CLI tools.
5. Refine it until both the validator and a human reviewer would consider it complete.
6. Wait for the next issue.

Your objective is to create issues that minimize implementation ambiguity and reduce follow-up questions during development.

---

## Related Workflows

- [AI Slop Audit](ai-slop-audit.md)
- [Issue Audit](issue-audit.md)
