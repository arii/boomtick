# Impact Analysis Integration Guide

To use the Boomtick Impact Analysis composite action in a consumer repository, follow these requirements.

## GitHub Action Usage

Reference the action in your workflow:

```yaml
- uses: arii/boomtick/mcp/actions/impact-analysis@main # or a specific version
  with:
    github_token: ${{ secrets.GITHUB_TOKEN }}
    gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
    pr_number: ${{ github.event.pull_request.number }}
    jules_api_key: ${{ secrets.JULES_API_KEY }}
```

## Required package.json Scripts

The action will check for the existence of these scripts in your root `package.json` before execution:

- `impact:analysis`: Runs the dependency-based impact analysis.
- `impact:build-main`: Builds the base branch (e.g., `main`) for visual comparison.
- `build:review`: Builds the current PR branch for visual comparison.
- `impact:gemini-code-review`: (Optional) Runs AI code review.
- `impact:github-models-code-review`: (Optional) Runs AI code review via GitHub Models.
- `impact:visual-diff`: Captures and compares screenshots.
- `impact:dom-diff`: Compares DOM structure.
- `impact:gemini-review`: (Optional) Runs AI visual review.
- `impact:github-models-review`: (Optional) Runs AI visual review via GitHub Models.

## Environment Variables

- `VISUAL_DIFF_THRESHOLD`: (Default: `1.5`) Percentage difference allowed before flagging a visual change.

## Secrets Required

- `GITHUB_TOKEN`: Standard GitHub token for PR comments and API access.
- `GEMINI_API_KEY`: Required for Gemini-based AI reviews.
- `JULES_API_KEY`: Required for session integration with Jules.
