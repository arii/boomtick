#!/usr/bin/env bash
set -euo pipefail

repo=$GITHUB_REPOSITORY
run=$(jq -r '.workflow_run | [
  .event, .conclusion, .workflow_id, .run_number, .run_attempt, .id,
  .head_branch, .head_sha, .html_url
] | @tsv' "$GITHUB_EVENT_PATH")
read -r event conclusion workflow_id number attempt run_id branch sha url <<< "$run"
if [[ "$event" != push || ( "$conclusion" != failure && "$conclusion" != success ) ]]; then
  exit 0
fi

# workflow_run delivery and concurrency scheduling are not ordered by CI run number.
for status in success failure; do
  latest=$(gh api --method GET "repos/$repo/actions/workflows/$workflow_id/runs" \
    -f branch="$branch" -f event=push -f status="$status" -F per_page=1 \
    --jq '.workflow_runs[0] // empty | [.run_number, .run_attempt] | @tsv')
  if [[ -n "$latest" ]]; then
    read -r latest_number latest_attempt <<< "$latest"
    if (( latest_number > number || (latest_number == number && latest_attempt > attempt) )); then
      echo "Ignoring superseded CI run $run_id (attempt $attempt)."
      exit 0
    fi
  fi
done

label=main-ci-failure
marker="<!-- ci-repair:$workflow_id:$branch -->"
issues=$(gh api --paginate --method GET "repos/$repo/issues" \
  -f labels="$label" -f state=open -F per_page=100 |
  jq -r --arg marker "$marker" '.[] |
    select(.pull_request == null and .user.type == "Bot") |
    select((.body // "" | split("\n") | index($marker)) != null) | .number')
run_url="$url/attempts/$attempt"

if [[ "$conclusion" == success ]]; then
  for issue in $issues; do
    gh issue close "$issue" --repo "$repo" --reason completed \
      --comment "CI recovered on `$branch` in [run $run_id (attempt $attempt)]($run_url)."
  done
  if [[ -z "$issues" ]]; then
    echo "CI passed on $branch; no open incident for workflow $workflow_id."
  fi
  exit 0
fi

issue=${issues%%$'\n'*}
if [[ -n "$issue" ]]; then
  recorded=$(gh issue view "$issue" --repo "$repo" --json body,comments |
    jq -r --arg link "]($run_url)" 'any(.body, .comments[].body; contains($link))')
  if [[ "$recorded" == true ]]; then
    echo "Run $run_id (attempt $attempt) already recorded in #$issue."
    exit 0
  fi
fi

jobs=$(gh api --paginate --method GET "repos/$repo/actions/runs/$run_id/attempts/$attempt/jobs" \
  -F per_page=100 | jq -sr '[.[].jobs[] | select(.conclusion == "failure") | .name] | join(", ")')
printf -v body 'CI failed in [run %s (attempt %s)](%s).\n\n**Commit:** %s\n**Failing jobs:** %s' \
  "$run_id" "$attempt" "$run_url" "$sha" "$jobs"
if [[ -n "$issue" ]]; then
  gh issue comment "$issue" --repo "$repo" --body "$body"
else
  existing_label=$(gh label list --repo "$repo" --search "$label" --json name \
    --jq '.[] | select(.name == "main-ci-failure") | .name')
  if [[ -z "$existing_label" ]]; then
    gh label create "$label" --repo "$repo" --color FF0000 --description "CI failures on the default branch"
  fi
  gh issue create --repo "$repo" --title "fix(ci): CI failure on $branch" --label "$label" \
    --body "$body"$'\n\n'"$marker"
fi
