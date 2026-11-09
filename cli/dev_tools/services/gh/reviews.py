"""GitHub reviews, comments, and labels."""

import json
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote
import requests
from dev_tools.constants import REVIEW_PLACEHOLDERS
from dev_tools.utils import CLIError, log_info, log_warn
from dev_tools.services.gh.issues import IssuesMixin


class ReviewsMixin(IssuesMixin):
    """GitHub reviews, comments, and labels."""

    def fetch_reviews(
        self, number: int, repo: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetches top-level PR reviews for a pull request."""
        target_repo = repo or self.repo
        return self._request("GET", f"/repos/{target_repo}/pulls/{number}/reviews")

    def fetch_pr_commits(
        self, number: int, repo: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetches commits for a pull request."""
        target_repo = repo or self.repo
        return self._request("GET", f"/repos/{target_repo}/pulls/{number}/commits")

    def fetch_review_comments(
        self, number: int, repo: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetches the review comments on a pull request."""
        target_repo = repo or self.repo
        return self._request("GET", f"/repos/{target_repo}/pulls/{number}/comments")

    def _get_diff_mapping(self, pr_number: int) -> Dict[str, Dict[int, int]]:
        """
        Parses the PR diff and returns a mapping of {filename: {new_line_number: diff_position}}.
        Diff position is 0-indexed starting from the first '@@' hunk header in the file.
        """
        diff_text = self.fetch_pr_diff(pr_number)
        mapping: Dict[str, Dict[int, int]] = {}
        current_file = None
        file_diff_pos = 0
        new_line_num = 0
        first_hunk_seen = False

        for line in diff_text.splitlines():
            if line.startswith("diff --git"):
                current_file = None
                first_hunk_seen = False
                continue
            if line.startswith("--- "):
                continue
            if line.startswith("+++ b/"):
                current_file = line[6:].strip()
                mapping[current_file] = {}
                file_diff_pos = 0
                continue
            if line.startswith("@@ "):
                if current_file is not None:
                    if not first_hunk_seen:
                        # First hunk of the file: hunk header is position 0
                        file_diff_pos = 0
                        first_hunk_seen = True
                    else:
                        # Subsequent hunk headers count as a line in the diff
                        file_diff_pos += 1

                    match = re.search(r"\+(\d+)", line)
                    if match:
                        new_line_num = int(match.group(1))
                continue

            if current_file is not None:
                file_diff_pos += 1
                if line.startswith("+"):
                    mapping[current_file][new_line_num] = file_diff_pos
                    new_line_num += 1
                elif line.startswith("-"):
                    # Deletions increment position but don't have a line number in the new file
                    pass
                elif line.startswith("\\"):
                    # "\ No newline at end of file" increments position
                    file_diff_pos += 1
                else:
                    # Context line
                    mapping[current_file][new_line_num] = file_diff_pos
                    new_line_num += 1
        return mapping

    def create_review(
        self, number: int, body: str, comments: List[Dict[str, Any]], event: str
    ) -> Dict[str, Any]:
        """Create a pull request review."""
        data = {"body": body, "event": event, "comments": comments}
        return self._request(
            "POST", f"/repos/{self.repo}/pulls/{number}/reviews", json_data=data
        )

    def add_labels(
        self, number: int, labels: List[str], repo: Optional[str] = None
    ) -> Dict[str, Any]:
        """Adds labels to an issue or pull request and returns the normalized issue dictionary."""
        target_repo = repo or self.repo
        if self.use_graphql:
            try:
                issue_node_id, resolved_labels = self._resolve_node_ids(number, labels)
                if issue_node_id and all(l in resolved_labels for l in labels):
                    label_ids = [resolved_labels[l] for l in labels]
                    query = """
                    mutation($labelableId: ID!, $labelIds: [ID!]!) {
                      addLabelsToLabelable(input: {labelableId: $labelableId, labelIds: $labelIds}) {
                        labelable {
                          __typename
                          ... on Issue {
                            number
                            title
                            url
                            state
                          }
                          ... on PullRequest {
                            number
                            title
                            url
                            state
                          }
                        }
                      }
                    }
                    """
                    variables = {
                        "labelableId": issue_node_id,
                        "labelIds": label_ids,
                    }
                    res = self.graphql(query, variables)
                    labelable = (
                        res.get("data", {})
                        .get("addLabelsToLabelable", {})
                        .get("labelable")
                        or {}
                    )
                    state = labelable.get("state")
                    if isinstance(state, str):
                        state = state.lower()
                    return {
                        "number": labelable.get("number"),
                        "title": labelable.get("title"),
                        "html_url": labelable.get("url"),
                        "state": state,
                    }
                log_warn(
                    "Could not resolve all node IDs for GraphQL add_labels. Falling back to REST."
                )
            except Exception as e:
                log_warn(f"GraphQL add_labels failed: {e}. Falling back to REST.")

        # Fallback to REST
        self._request(
            "POST",
            f"/repos/{target_repo}/issues/{number}/labels",
            json_data={"labels": labels},
        )
        issue_data = self.fetch_issue_details(number, repo=target_repo)
        return self._normalize_issue_response(issue_data)

    def remove_label(
        self, number: int, label_name: str, repo: Optional[str] = None
    ) -> Dict[str, Any]:
        """Removes a label from an issue or pull request and returns the normalized issue dictionary."""
        target_repo = repo or self.repo
        if self.use_graphql:
            try:
                issue_node_id, resolved_labels = self._resolve_node_ids(
                    number, [label_name]
                )
                if issue_node_id and label_name in resolved_labels:
                    label_id = resolved_labels[label_name]
                    query = """
                    mutation($labelableId: ID!, $labelIds: [ID!]!) {
                      removeLabelsFromLabelable(input: {labelableId: $labelableId, labelIds: $labelIds}) {
                        labelable {
                          __typename
                          ... on Issue {
                            number
                            title
                            url
                            state
                          }
                          ... on PullRequest {
                            number
                            title
                            url
                            state
                          }
                        }
                      }
                    }
                    """
                    variables = {
                        "labelableId": issue_node_id,
                        "labelIds": [label_id],
                    }
                    res = self.graphql(query, variables)
                    labelable = (
                        res.get("data", {})
                        .get("removeLabelsFromLabelable", {})
                        .get("labelable")
                        or {}
                    )
                    state = labelable.get("state")
                    if isinstance(state, str):
                        state = state.lower()
                    return {
                        "number": labelable.get("number"),
                        "title": labelable.get("title"),
                        "html_url": labelable.get("url"),
                        "state": state,
                    }
                log_warn(
                    f"Could not resolve label node ID for '{label_name}' under GraphQL. Falling back to REST."
                )
            except Exception as e:
                log_warn(f"GraphQL remove_label failed: {e}. Falling back to REST.")

        # Fallback to REST
        encoded_label = quote(label_name)
        self._request(
            "DELETE", f"/repos/{target_repo}/issues/{number}/labels/{encoded_label}"
        )
        issue_data = self.fetch_issue_details(number, repo=target_repo)
        return self._normalize_issue_response(issue_data)

    @staticmethod
    def validate_review_payload(payload: Dict[str, Any]):
        """
        Validates that the review payload is not just boilerplate or empty.
        """

        if not isinstance(payload, dict):
            raise CLIError("Review rejected: Invalid payload format (expected dict).")

        body = payload.get("body", "")
        if not isinstance(body, str):
            body = str(body)

        recommendation = payload.get("recommendation", "")
        if not isinstance(recommendation, str):
            recommendation = str(recommendation)

        comments = payload.get("comments", [])
        if not isinstance(comments, list):
            raise CLIError("Review rejected: 'comments' must be a list.")

        # Check recommendation for placeholders (should be explicit)
        for p in REVIEW_PLACEHOLDERS:
            if re.search(p, recommendation, re.IGNORECASE):
                raise CLIError(
                    f"Review rejected: Recommendation contains boilerplate placeholder matching '{p}'"
                )

        # Check for real comments (not placeholders)
        real_comments = []
        for c in comments:
            if not isinstance(c, dict):
                continue

            c_body = str(c.get("body", ""))
            c_path = str(c.get("path", ""))

            # Check if comment fields contain placeholders
            is_placeholder = False
            for p in REVIEW_PLACEHOLDERS:
                if re.search(p, c_body, re.IGNORECASE) or re.search(
                    p, c_path, re.IGNORECASE
                ):
                    is_placeholder = True
                    break

            if is_placeholder:
                raise CLIError(
                    "Review rejected: Comment contains boilerplate placeholder."
                )

            if c_body.strip() and not re.search(
                r"<filename\s*/?>", c_path, re.IGNORECASE
            ):
                real_comments.append(c)

        # Check for empty/meaningless body
        clean_body = body
        clean_body = re.sub(r"^#+.*$", "", clean_body, flags=re.MULTILINE)
        # Strip all placeholders for meaningful content check
        for p in REVIEW_PLACEHOLDERS:
            clean_body = re.sub(p, "", clean_body, flags=re.IGNORECASE | re.DOTALL)

        clean_body = clean_body.strip()

        if not clean_body and not real_comments:
            raise CLIError(
                "Review rejected: No meaningful content found in body or comments."
            )

    def submit_pr_review(
        self,
        pr_number: int,
        filepath: str,
        cleanup: bool = False,
        dry_run: bool = True,
        event_override: Optional[str] = None,
        is_json: bool = False,
    ):
        """
        Submits a PR review from a markdown file containing a JSON payload.
        The file should have standard Markdown at the top and a JSON block at the bottom for metadata.
        """

        if not os.path.exists(filepath):
            raise CLIError(f"Review file missing: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        payload = self._extract_review_payload(content)
        self.validate_review_payload(payload)

        self._map_review_comments(pr_number, payload)

        pr_details = self.fetch_pr_details(pr_number)
        check_runs = self.fetch_check_runs(pr_details.get("head", {}).get("sha"))
        failing_checks = [
            str(run.get("name"))
            for run in check_runs
            if run.get("conclusion") == "failure"
        ]

        event = self._determine_review_event(payload, failing_checks, event_override)

        if not dry_run:

            def try_create_review(review_body, review_comments, review_event):
                try:
                    return self.create_review(
                        pr_number, review_body, review_comments, review_event
                    )
                except (requests.exceptions.HTTPError, CLIError) as e:
                    code = getattr(e, "code", None)
                    if (
                        code is None
                        and isinstance(e, requests.exceptions.HTTPError)
                        and e.response is not None
                    ):
                        code = e.response.status_code

                    if code == 422:
                        error_data = getattr(e, "data", None)
                        if (
                            error_data is None
                            and isinstance(e, requests.exceptions.HTTPError)
                            and e.response is not None
                        ):
                            try:
                                error_data = e.response.json()
                            except Exception as inner_e:
                                log_warn(
                                    f"Failed to parse error response JSON: {inner_e}"
                                )

                        error_msg = (
                            json.dumps(error_data)
                            if error_data
                            else (
                                e.response.text
                                if hasattr(e, "response") and e.response
                                else str(e)
                            )
                        )

                        if (
                            "Can not approve your own pull request" in error_msg
                            and review_event != "COMMENT"
                        ):
                            log_warn("Cannot approve own PR. Retrying as COMMENT...")
                            return try_create_review(
                                review_body, review_comments, "COMMENT"
                            )

                        # Handle individual comment failures if possible, or fallback to body
                        if review_comments:
                            log_warn(
                                (
                                    f"Failed "
                                    f"to post "
                                    f"{len(review_comments)} inline "
                                    f"comments. Retrying "
                                    f"as body "
                                    f"comments. Error: "
                                    f"{error_msg[:200]}"
                                )
                            )
                            fallback_body = review_body
                            fallback_body += "\n\n### Inline Comments (Fallback due to line resolution errors)\n"
                            for comment in review_comments:
                                line_info = (
                                    f":{comment.get('line')}"
                                    if comment.get("line")
                                    else ""
                                )
                                fallback_body += f"- **{comment.get('path')}{line_info}**: {comment.get('body')}\n"
                            return try_create_review(fallback_body, [], review_event)
                    raise e

            try_create_review(
                payload.get("body", ""), payload.get("comments", []), event
            )

            if event == "REQUEST_CHANGES":
                labels = [
                    l.get("name") if isinstance(l, dict) else l
                    for l in pr_details.get("labels", [])
                ]
                if "needs-design-system-fix" not in labels and any(
                    k in payload.get("body", "").lower() for k in ["tailwind", "token"]
                ):
                    self.add_labels(pr_number, ["needs-design-system-fix"])

            if not is_json:
                log_info(f"✅ Submitted {event} for PR #{pr_number}")

            if cleanup:
                if os.path.exists(filepath):
                    os.remove(filepath)
                ctx = filepath.replace("pr-review-", "pr-context-")
                if os.path.exists(ctx):
                    os.remove(ctx)
        else:
            if not is_json:
                log_info(f"[DRY-RUN] Would submit {event} for PR #{pr_number}")

        return {"status": "success", "event": event, "pr": pr_number}

    def _extract_review_payload(self, content: str) -> Dict[str, Any]:

        json_blocks = list(re.finditer(r"```json\n(.*?)\n```", content, re.DOTALL))
        if not json_blocks:
            raise CLIError("Could not find any JSON block in review document")

        METADATA_IDENTIFIER_KEYS = {"recommendation", "comments", "labels"}

        payload = None
        metadata_match = None
        for match in reversed(json_blocks):
            try:
                candidate = json.loads(match.group(1))
                if isinstance(candidate, dict) and any(
                    k in candidate for k in METADATA_IDENTIFIER_KEYS
                ):
                    payload = candidate
                    metadata_match = match
                    break
            except json.JSONDecodeError:
                continue

        if not payload or not metadata_match:
            raise CLIError(
                f"Could not find a valid JSON metadata block (expected keys: {', '.join(METADATA_IDENTIFIER_KEYS)})"
            )

        body = content[: metadata_match.start()].strip()
        body = re.split(r"##\s+Output JSON", body, flags=re.IGNORECASE)[0].strip()

        for p in REVIEW_PLACEHOLDERS:
            body = re.sub(p, "", body, flags=re.IGNORECASE | re.DOTALL).strip()

        if not body:
            raise CLIError(
                "Review body (Markdown section) is empty. Provide findings before the JSON block."
            )

        json_body = payload.get("body", "").strip()

        if json_body:
            stripped_body = json_body
            for p in REVIEW_PLACEHOLDERS:
                stripped_body = re.sub(
                    p, "", stripped_body, flags=re.IGNORECASE | re.DOTALL
                ).strip()

            if not stripped_body:
                raise CLIError(
                    "Review rejected: JSON body contains only placeholders/boilerplate. "
                    "Ensure you provide actual feedback in the 'body' field of the JSON block."
                )

            payload["body"] = f"{body}\n\n{stripped_body}"
        else:
            payload["body"] = body

        return payload

    def _map_review_comments(self, pr_number: int, payload: Dict[str, Any]) -> None:

        try:
            diff_mapping = self._get_diff_mapping(pr_number)
            mapped_comments = []
            unmapped_comments = []

            for comment in payload.get("comments", []):
                path = comment.get("path")
                line = comment.get("line")

                if path in diff_mapping and line in diff_mapping[path]:
                    comment["position"] = diff_mapping[path][line]
                    mapped_comments.append(comment)
                else:
                    unmapped_comments.append(comment)

            payload["comments"] = mapped_comments

            if unmapped_comments:
                extra_body = "\n\n### Additional Feedback (Lines not found in diff)\n"
                for c in unmapped_comments:
                    extra_body += (
                        f"- **{c.get('path')}:{c.get('line')}**: {c.get('body')}\n"
                    )
                payload["body"] = payload.get("body", "") + extra_body

        except Exception as e:
            log_warn(f"Failed to generate diff mapping for PR #{pr_number}: {e}")

    def _determine_review_event(
        self,
        payload: Dict[str, Any],
        failing_checks: List[str],
        event_override: Optional[str] = None,
    ) -> str:
        recommendation = payload.get("recommendation", "")
        if event_override:
            event = event_override
        elif recommendation == "Approved":
            event = "APPROVE"
        elif recommendation == "Approved with Minor Changes":
            event = "COMMENT"
        elif recommendation == "Not Approved":
            event = "REQUEST_CHANGES"
        else:
            event = (
                "REQUEST_CHANGES"
                if "Not Approved" in payload.get("body", "")
                else "APPROVE"
                if "Approved" in payload.get("body", "")
                else "COMMENT"
            )

        if failing_checks and event == "APPROVE":
            event = "COMMENT"
            warning = (
                f"> "
                f"⚠️ **BLOCKING "
                f"CI FAILURE**: "
                f"Approval overridden "
                f"to COMMENT "
                f"because the "
                f"following checks "
                f"are failing: "
                f"{', '.join(failing_checks)}. Please "
                f"resolve CI "
                f"issues before "
                f"approval.\n\n"
            )
            payload["body"] = warning + payload.get("body", "")

        return event

    def fetch_pr_review_decision(
        self, number: int, repo: Optional[str] = None
    ) -> Optional[str]:
        """
        Determines the review decision ('APPROVED', 'CHANGES_REQUESTED', 'REVIEW_REQUIRED', or None).
        Attempts to query GraphQL for reviewDecision first, falling back to REST reviews.
        """
        target_repo = repo or self.repo
        if "/" in str(target_repo):
            owner, repo_name = str(target_repo).split("/", 1)
            query = """
            query getPrReviewDecision($owner: String!, $repo: String!, $prNumber: Int!) {
              repository(owner: $owner, name: $repo) {
                pullRequest(number: $prNumber) {
                  reviewDecision
                }
              }
            }
            """
            try:
                res = self._request(
                    "POST",
                    "/graphql",
                    json_data={
                        "query": query,
                        "variables": {
                            "owner": owner,
                            "repo": repo_name,
                            "prNumber": number,
                        },
                    },
                )
                pr_node = res.get("data", {}).get("repository", {}).get("pullRequest")
                if pr_node and "reviewDecision" in pr_node:
                    return pr_node.get("reviewDecision")
            except Exception as e:
                log_warn(f"github: review-decision query failed for PR #{number}: {e}")

        # Fallback to REST reviews
        try:
            reviews = self.fetch_reviews(number, repo=target_repo)
            # Find the latest review state per user
            user_reviews: Dict[str, str] = {}
            for r in reviews:
                user = r.get("user", {}).get("login")
                state = r.get("state")
                if user and state in (
                    "APPROVED",
                    "CHANGES_REQUESTED",
                    "COMMENTED",
                    "DISMISSED",
                ):
                    if state != "COMMENTED":
                        user_reviews[user] = state
            states = list(user_reviews.values())
            if any(s == "CHANGES_REQUESTED" for s in states):
                return "CHANGES_REQUESTED"
            if any(s == "APPROVED" for s in states):
                return "APPROVED"
        except Exception as e:
            log_warn(f"github: review-states query failed: {e}")
        return None
