# Continue Migrating Composite GitHub Actions from Boomtick

## UNDERSTAND THE ISSUE

The `boomtick` repository acts as a foundation for developer tooling and AI review frameworks. While it provides essential capabilities for autonomous agents, many downstream repositories continue integrating it exclusively as a git submodule. This creates friction around submodule pointers, updates, and initialization. A planned architectural shift involves exposing these operations via Composite GitHub Actions to support "zero-submodule integration", decoupling workflows from direct filesystem dependency trees. However, while some actions exist (e.g. `setup-env`, `setup-all`, `setup-workspace`), a full migration of all core operational workflows to composite actions remains incomplete.

## DETERMINE APPROACH

1. **Audit Existing Workflows:** Identify remaining GitHub Actions workflows in `.github/workflows/` (such as `chatops-trigger.yml`, `ci-repair.yml`, `issue-operations.yml`) and encapsulate their core logic into `.github/actions/` composite actions.
2. **Abstract Execution Paths:** Ensure that scripts invoked within these composite actions resolve paths dynamically relative to `github.action_path` rather than relying on submodule-specific paths like `boomtick-pkg/scripts/`.
3. **Refactor Workflow YAMLs:** Update the existing workflows in `.github/workflows/` to utilize these newly created composite actions, serving as both integration tests and reference implementations.
4. **Update Documentation:** Revise `docs/onboarding.md` and `README.md` to document the new zero-submodule composite action integration strategy.

## SPECIFY SCOPE

- Creating composite actions in `.github/actions/` for remaining core operations (e.g. CI repair, chatops, AI reviews).
- Updating existing `.github/workflows/*.yml` to consume these composite actions.
- Updating `docs/onboarding.md` to reflect the new integration method.

## DEFINITION OF DONE

- All major AI orchestration and CI feedback steps are available as composite actions under `.github/actions/`.
- Path resolution logic within composite actions utilizes `${{ github.action_path }}` safely and robustly.
- Existing internal `.github/workflows/` consume the new composite actions.
- Documentation in `docs/onboarding.md` explains how to integrate via composite actions instead of just as a submodule.
- All CI validations and schema verifications pass successfully.
