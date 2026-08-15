This PR updates the onboarding documentation in the boomtick repository to reflect the Zero-Submodule Strategy, which utilizes @main tracking for direct GitHub Actions integrations. It also adds the necessary # nosemgrep suppressions to the current repository's workflows so that using @main tags for internal composite actions does not trigger security warnings in CI. Finally, it creates two implementation-ready design issues (issue-tech-dancer-integration.md and issue-portfolio-integration.md) for the downstream repositories so that their respective integrations (and pnpm dependencies/config initialization) can be updated to match the new architecture.

.github/workflows/agent-orchestrator.yml
.github/workflows/chatops-trigger.yml
.github/workflows/ci.yml
.github/workflows/release.yml
.github/workflows/smoke-test-impact-analysis.yml
