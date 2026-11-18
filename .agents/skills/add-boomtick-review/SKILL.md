---
name: add-boomtick-review
description: Add opt-in BoomTick AI review to a GitHub repository with a pinned action, one Gemini secret, and the built-in GitHub token. Use when setting up or checking the BoomTick review integration.
---

# Add BoomTick review

## Check before editing

1. Inspect the target repo's workflows for an existing review job; don't add a second one. Check that Docker-based actions are allowed on its GitHub-hosted Linux runner.
2. Verify the pin against [BoomTick](https://github.com/arii/boomtick). The root Docker action defaults to the built-in GitHub token and the pull request number from the event; `gemini-api-key` is the only required input. Pin a reviewed commit that supports these defaults. Don't silently fall back to `@main`.
3. Ask the owner to approve sending review context to Gemini and any API spend. Have them add `GEMINI_API_KEY` under **Settings → Secrets and variables → Actions** and create the opt-in `boomtick-review` label. Never put the key in Git, workflow input, or terminal output.

## Add the workflow

Use `.github/workflows/boomtick-review.yml`:

```yaml
name: BoomTick review

on:
  pull_request:
    types: [labeled]

jobs:
  review:
    if: >-
      github.event.label.name == 'boomtick-review' &&
      github.event.pull_request.head.repo.full_name == github.repository &&
      github.event.pull_request.base.ref == github.event.repository.default_branch
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: arii/boomtick@58f417981cf698995871cc4e906d0e12833bdb19
        with:
          gemini-api-key: ${{ secrets.GEMINI_API_KEY }}
```

A maintainer adds the label to review a trusted same-repo PR. Ordinary pushes and forks don't trigger the review job. Keep checkout on GitHub's default PR merge commit with `fetch-depth: 0`: the action diffs against the base branch and can skip the review if shallow history hides it. Don't switch to `pull_request_target`, give forks secrets, or run project scripts in this job.

The trigger is the label being added, not the label being present. After new commits land, remove and reapply the label if a maintainer wants another review of the updated diff.

## Verify on an approved run

- Validate the workflow with `actionlint` before opening the setup PR. Explain the permissions and model cost in the PR.
- After the owner merges the workflow, add the label to a small trusted PR with an actual code change and no sensitive data. Confirm the job succeeds and the review appears on that PR; a green run alone isn't proof that it posted.
- BoomTick can post an approval or request changes. Check the repo's Actions token policy and branch protection with the owner before enabling this. Don't count the bot as a substitute for a human reviewer. If posting fails or the policy blocks the review, stop and report the precise error rather than broadening permissions.
