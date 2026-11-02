# pylint: disable=arguments-differ,attribute-defined-outside-init,line-too-long,logging-fstring-interpolation,missing-docstring,too-few-public-methods,too-many-branches,too-many-locals,too-many-statements
import logging
import re
import sys
from typing import Any, Dict, List, Optional

from dev_tools.orchestrator import Orchestrator
from dev_tools.services.github import GitHubClient
from dev_tools.services.jules import JulesClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_ECOSYSTEM_REPOS = [
    "arii/remote-server",
    "arii/tech-dancer",
    "arii/boomtick",
]


class ExtendedJulesClient(JulesClient):
    """JulesClient subclass with extended timeouts for daemon use."""

    def get_messages(self, session_id: str, timeout: int = 30) -> List[Dict[str, Any]]:
        # Set default timeout to 30s instead of the default 10s
        return super().get_messages(session_id, timeout=timeout)

    def get_activities(self, session_id: str, timeout: int = 30) -> List[Dict[str, Any]]:
        return super().get_activities(session_id, timeout=timeout)


class AutonomousTriageDaemon:
    """
    Autonomous Multi-Repo Triage Daemon adhering to docs/autonomous-triage-runbook.md:
    1. Jules Session Inspection, Plan Nudging (AWAITING_USER_FEEDBACK), and CI Feedback
    2. Empty PR Detection & Remediation
    3. Multi-Repo PR Evaluation & Auto-Merge (all green CI, mergeable == MERGEABLE)
    4. Stale Issue / CI Failure Cleanup (closing orphan failure issues for merged PRs)
    5. Concurrency-Gated Backlog Dispatching (label candidate issue with 'jules')
    """

    def __init__(self, repos: Optional[List[str]] = None):
        self.repos = repos
        self.jules = ExtendedJulesClient()
        self.github = GitHubClient()
        self.orchestrator = Orchestrator()
        self.orchestrator.initialize_jules(self.jules)
        self._pr_cache: Dict[Any, Any] = {}
        self._session_to_pr_map: Dict[str, Any] = {}

    def get_configured_repos(self) -> List[str]:
        if self.repos:
            return self.repos
        if DEFAULT_ECOSYSTEM_REPOS:
            return list(DEFAULT_ECOSYSTEM_REPOS)
        return [self.github.repo] if getattr(self.github, "repo", None) else []

    def run_triage(
        self,
        limit: int = 10,
        concurrency_limit: int = 2,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        target_repos = self.get_configured_repos()
        logger.info(f"Starting Autonomous Triage Pass across repos: {target_repos}")
        results: Dict[str, Any] = {
            "status": "success",
            "sessions_evaluated": 0,
            "sessions_nudged": [],
            "empty_prs_handled": [],
            "prs_merged": [],
            "stale_issues_closed": [],
            "backlog_dispatched": [],
        }

        # Fetch sessions
        sessions = []
        try:
            sessions = self.jules.list_sessions(pageSize=limit)
            results["sessions_evaluated"] = len(sessions)
            logger.info(f"Found {len(sessions)} Jules sessions")
        except Exception as e:
            logger.error(f"Error fetching sessions from Jules API: {e}")

        self._pr_cache.clear()
        self._session_to_pr_map.clear()
        self._pre_match_sessions_batch(sessions)

        # Phase 1 & 2: Jules Session Inspection & Nudge / CI Feedback
        for session in sessions:
            self._process_session(session, results=results, dry_run=dry_run)

        # Phase 3: Multi-Repo PR Evaluation & Auto-Merge
        self._evaluate_and_merge_prs(target_repos=target_repos, results=results, dry_run=dry_run)

        # Phase 4: Stale CI Cleanup
        self._cleanup_stale_ci_issues(target_repos=target_repos, results=results, dry_run=dry_run)

        # Phase 5: Concurrency-Gated Backlog Dispatch
        self._dispatch_backlog(
            sessions=sessions,
            concurrency_limit=concurrency_limit,
            target_repos=target_repos,
            results=results,
            dry_run=dry_run,
        )

        logger.info(f"Autonomous Triage Pass completed: {results}")
        return results

    def run(self, limit: int = 10, concurrency_limit: int = 2, dry_run: bool = False):
        """Standard daemon entrypoint for backward compatibility and feedback check."""
        return self.run_triage(limit=limit, concurrency_limit=concurrency_limit, dry_run=dry_run)

    def _pre_match_sessions_batch(self, sessions: List[Dict[str, Any]]):
        """Batch search for multiple session IDs in one GitHub API call across repos."""
        if not sessions:
            return

        session_ids = []
        for s in sessions:
            sid = s.get("name", "").split("/")[-1]
            if sid:
                session_ids.append(sid)

        if not session_ids:
            return

        batch_size = 5
        for i in range(0, len(session_ids), batch_size):
            chunk = session_ids[i : i + batch_size]
            id_query = " OR ".join([f'"{sid}"' for sid in chunk])
            full_query = f"({id_query}) in:body,title state:open"

            try:
                logger.info(f"Performing batch PR search for {len(chunk)} session IDs")
                found_prs = self.github.search_pull_requests(full_query, limit=50)

                for pr in found_prs:
                    body = (pr.get("body") or "").lower()
                    title = (pr.get("title") or "").lower()
                    for sid in chunk:
                        if sid.lower() in body or sid.lower() in title:
                            self._session_to_pr_map[sid] = pr
                            self._pr_cache[(self.github.repo, pr["number"])] = pr
            except Exception as e:
                logger.warning(f"Batch PR search failed for chunk: {e}")

    def _get_pr_for_session(self, session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Optimized PR lookup for a session."""
        session_id = session.get("name", "").replace("sessions/", "")

        # 0. Check batch pre-match results
        if session_id in self._session_to_pr_map:
            return self._session_to_pr_map[session_id]

        # 1-3. Delegate to orchestrator logic
        pr_num = self.orchestrator.get_pr_for_session(session)
        if pr_num:
            repo = self.orchestrator.get_repo_for_session(session) or self.github.repo
            cache_key = (repo, pr_num)
            if cache_key not in self._pr_cache:
                try:
                    self._pr_cache[cache_key] = self.github.fetch_pr_details(pr_num, repo=repo)
                except Exception as e:
                    logger.warning(f"Could not fetch PR #{pr_num} for session {session_id} in {repo}: {e}")
                    return None
            return self._pr_cache[cache_key]

        return None

    def _process_session(
        self,
        session: Dict[str, Any],
        results: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
    ):
        session_id = session.get("name", "").replace("sessions/", "")
        if not session_id:
            return

        state = session.get("state")
        logger.info(f"Processing session {session_id} (state: {state})")

        # 1. Plan Approval / Nudging when AWAITING_USER_FEEDBACK
        if state == "AWAITING_USER_FEEDBACK":
            self._nudge_session_if_needed(session, results=results, dry_run=dry_run)
            return

        # 2. Check associated PR and CI feedback if applicable
        matched_pr = self._get_pr_for_session(session)
        if not matched_pr:
            logger.info(f"No matching PR found for session {session_id}")
            return

        pr_num = matched_pr["number"]
        repo = self.orchestrator.get_repo_for_session(session) or self.github.repo
        logger.info(f"Matched PR #{pr_num} ({matched_pr.get('headRefName')}) for session {session_id}")

        # Check for empty PR
        try:
            view_details = self.github.fetch_pr_view_details(pr_num, repo=repo)
            files = view_details.get("files", [])
            if isinstance(files, list) and len(files) == 0:
                logger.warning(f"Empty PR detected: #{pr_num} in {repo} (0 files changed)")
                if results is not None:
                    results["empty_prs_handled"].append({"repo": repo, "pr": pr_num, "session": session_id})
                if not dry_run:
                    close_comment = "Automated triage: Closed empty PR with 0 files changed."
                    self.github.close_pr(pr_num, repo=repo, comment=close_comment)
                return
        except Exception as e:
            logger.warning(f"Error checking files for PR #{pr_num}: {e}")

        # Trigger CI failure feedback
        try:
            res = self.orchestrator.trigger_jules_feedback(session_id)
            logger.info(f"Feedback trigger result for {session_id}: {res.get('status', 'unknown')}")
        except Exception as e:
            logger.error(f"Error triggering feedback for {session_id}: {e}")

    def _nudge_session_if_needed(
        self,
        session: Dict[str, Any],
        results: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
    ):
        session_id = session.get("name", "").replace("sessions/", "")
        logger.info(f"Inspecting AWAITING_USER_FEEDBACK session {session_id} activities")
        try:
            activities = self.jules.get_activities(session_id)
        except Exception as e:
            logger.error(f"Failed to fetch activities for session {session_id}: {e}")
            return

        # Determine if Jules has proposed a plan or is awaiting approval
        has_plan = False
        last_message = ""
        for act in activities:
            if act.get("planGenerated"):
                has_plan = True
            if act.get("userMessaged"):
                um = act["userMessaged"]
                if isinstance(um, str):
                    last_message = um
                elif isinstance(um, dict):
                    user_msg = um.get("userMessage", "")
                    last_message = user_msg.get("body", "") if isinstance(user_msg, dict) else user_msg

        # Check if already approved recently to avoid double-nudging
        approval_prompt = (
            "Plan looks great! Please proceed with implementation, verify syntax, ensure unit tests pass, and submit the pull request."
        )
        if last_message.strip() == approval_prompt.strip():
            logger.info(f"Session {session_id} was already approved with identical prompt. Skipping.")
            return

        logger.info(f"Nudging session {session_id} with plan approval prompt (has_plan={has_plan})")
        if results is not None:
            results["sessions_nudged"].append({"session": session_id, "has_plan": has_plan})

        if not dry_run:
            try:
                self.jules.send_message(session_id, approval_prompt)
                logger.info(f"Successfully nudged session {session_id}")
            except Exception as e:
                logger.error(f"Failed to send nudge message to session {session_id}: {e}")

    def _evaluate_and_merge_prs(
        self,
        target_repos: Optional[List[str]] = None,
        results: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
    ):
        """Query open PRs across configured repos, check rollup, promote draft, and auto-merge."""
        repos = target_repos or self.get_configured_repos()
        for repo in repos:
            try:
                open_prs = self.github.list_pull_requests(state="open", limit=50, repo=repo)
            except Exception as e:
                logger.warning(f"Could not list open PRs for repo {repo}: {e}")
                continue

            for pr in open_prs:
                pr_num = pr.get("number")
                if not pr_num:
                    continue

                try:
                    view_data = self.github.fetch_pr_view_details(pr_num, repo=repo)
                    if not view_data:
                        continue

                    # 1. Empty PR check
                    files = view_data.get("files", [])
                    if isinstance(files, list) and len(files) == 0:
                        logger.warning(f"Empty PR detected #{pr_num} in {repo}. Closing.")
                        if results is not None:
                            results["empty_prs_handled"].append({"repo": repo, "pr": pr_num})
                        if not dry_run:
                            self.github.close_pr(pr_num, repo=repo, comment="Automated triage: closed empty PR.")
                        continue

                    # 2. Mergeability check
                    mergeable = view_data.get("mergeable")
                    if mergeable != "MERGEABLE":
                        logger.info(f"PR #{pr_num} in {repo} is not MERGEABLE (status: {mergeable}). Skipping merge.")
                        continue

                    # 3. Status check rollup
                    rollup = view_data.get("statusCheckRollup", [])
                    if not self._is_rollup_green(rollup):
                        logger.info(f"PR #{pr_num} in {repo} has failing or pending checks. Skipping merge.")
                        continue

                    # If checks are green and mergeable == MERGEABLE:
                    logger.info(f"PR #{pr_num} in {repo} is fully validated and ready for merge.")

                    # Promote from draft if needed
                    is_draft = view_data.get("isDraft", False)
                    if is_draft:
                        logger.info(f"Promoting draft PR #{pr_num} in {repo} to ready")
                        if not dry_run:
                            self.github.mark_pr_ready(pr_num, repo=repo)

                    # Merge PR
                    logger.info(f"Executing auto-merge for PR #{pr_num} in {repo}")
                    if results is not None:
                        results["prs_merged"].append({"repo": repo, "pr": pr_num})

                    if not dry_run:
                        merged = self.github.merge_pr(pr_num, repo=repo, method="merge", delete_branch=True)
                        if merged:
                            # Close corresponding issue if referenced in body and not closed
                            self._close_linked_issues(view_data, repo=repo)

                except Exception as e:
                    logger.error(f"Error evaluating PR #{pr_num} in {repo}: {e}")

    def _is_rollup_green(self, rollup: List[Dict[str, Any]]) -> bool:
        """
        Check that statusCheckRollup has 0 failing, 0 pending, and allowed SKIPPED/NEUTRAL conclusions.
        """
        if not rollup:
            # If there are no checks configured, cannot confirm green
            return False

        for check in rollup:
            status = check.get("status", "")
            conclusion = check.get("conclusion")

            # Check pending
            if status in ("IN_PROGRESS", "QUEUED", "PENDING", "WAITING", "REQUESTED"):
                return False

            # Check failing
            if conclusion in ("FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"):
                return False

            # Valid conclusions are SUCCESS, NEUTRAL, SKIPPED
            if conclusion not in ("SUCCESS", "NEUTRAL", "SKIPPED") and status != "COMPLETED":
                return False

        return True

    def _close_linked_issues(self, pr_view_data: Dict[str, Any], repo: str):
        """Find linked issues (Fixes #123, Closes #123) and close them if still open."""
        body = pr_view_data.get("body", "")
        pr_num = pr_view_data.get("number")
        if not body:
            return

        linked_issue_nums = set(re.findall(r"(?:fixes|closes|resolves)\s+#(\d+)", body, re.IGNORECASE))
        for issue_num_str in linked_issue_nums:
            issue_num = int(issue_num_str)
            try:
                issue_data = self.github.fetch_issue_details(issue_num, repo=repo)
                if issue_data.get("state") == "open":
                    logger.info(f"Closing linked issue #{issue_num} in {repo} resolved by PR #{pr_num}")
                    close_comment = f"Resolved by PR #{pr_num}"
                    self.github.close_issue(issue_num, repo=repo, comment=close_comment)
            except Exception as e:
                logger.warning(f"Could not close linked issue #{issue_num} in {repo}: {e}")

    def _cleanup_stale_ci_issues(
        self,
        target_repos: Optional[List[str]] = None,
        results: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
    ):
        """Query open ci-failure issues. If the associated PR has merged, close the issue."""
        repos = target_repos or self.get_configured_repos()
        for repo in repos:
            try:
                ci_issues = self.github.list_issues(state="open", labels=["ci-failure"], repo=repo)
            except Exception as e:
                logger.warning(f"Could not list ci-failure issues for {repo}: {e}")
                continue

            for issue in ci_issues:
                issue_num = issue.get("number")
                title = issue.get("title", "")
                body = issue.get("body", "")

                # Look for PR number in title or body
                pr_match = re.search(r"PR\s+#?(\d+)", title, re.IGNORECASE) or re.search(r"PR\s+#?(\d+)", body, re.IGNORECASE)
                if not pr_match:
                    continue

                associated_pr_num = int(pr_match.group(1))
                try:
                    pr_data = self.github.fetch_pr_details(associated_pr_num, repo=repo)
                    # Check if merged
                    if pr_data.get("merged") is True or pr_data.get("state") == "closed":
                        logger.info(
                            f"Stale ci-failure issue #{issue_num} in {repo} for merged/closed PR #{associated_pr_num}. Closing."
                        )
                        if results is not None:
                            results["stale_issues_closed"].append(
                                {"repo": repo, "issue": issue_num, "pr": associated_pr_num}
                            )
                        if not dry_run and issue_num is not None:
                            comment = f"Automated triage: Associated PR #{associated_pr_num} has been resolved/merged. Closing orphan failure issue."
                            self.github.close_issue(issue_num, repo=repo, comment=comment)
                except Exception as e:
                    logger.warning(f"Failed to check associated PR #{associated_pr_num} for issue #{issue_num}: {e}")

    def _dispatch_backlog(
        self,
        sessions: List[Dict[str, Any]],
        concurrency_limit: int = 2,
        target_repos: Optional[List[str]] = None,
        results: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
    ):
        """
        Count active sessions (IN_PROGRESS or AWAITING_USER_FEEDBACK).
        If below concurrency threshold, query open backlog issues lacking jules label and dispatch.
        """
        active_count = 0
        for s in sessions:
            st = s.get("state")
            if st in ("IN_PROGRESS", "AWAITING_USER_FEEDBACK", "PENDING", "QUEUED"):
                active_count += 1

        logger.info(f"Current active Jules sessions: {active_count}/{concurrency_limit}")
        if active_count >= concurrency_limit:
            logger.info("Concurrency limit reached. Skipping backlog dispatch.")
            return

        available_slots = concurrency_limit - active_count

        # Prioritize repositories in order (e.g. remote-server first, then tech-dancer, boomtick)
        repos = target_repos or self.get_configured_repos()
        for repo in repos:
            if available_slots <= 0:
                break

            try:
                open_issues = self.github.list_issues(state="open", limit=30, repo=repo)
            except Exception as e:
                logger.warning(f"Could not list open backlog issues for {repo}: {e}")
                continue

            for issue in open_issues:
                if available_slots <= 0:
                    break

                issue_num = issue.get("number")
                title = issue.get("title", "")
                labels = [l.lower() for l in issue.get("labels", [])]

                # Lacks 'jules' label
                if "jules" in labels:
                    continue

                # Exclude meta-issues, epics, or ci-failures
                if any(excluded in labels for excluded in ("ci-failure", "epic", "wontfix", "blocked", "meta")):
                    continue
                if any(k in title.lower() for k in ("burndown", "decommission", "meta:", "[epic]")):
                    continue

                logger.info(f"Dispatching backlog issue #{issue_num} ({title}) in {repo} by adding 'jules' label")
                if results is not None:
                    results["backlog_dispatched"].append({"repo": repo, "issue": issue_num, "title": title})

                if not dry_run and issue_num is not None:
                    try:
                        self.github.add_labels(issue_num, ["jules"], repo=repo)
                        available_slots -= 1
                    except Exception as e:
                        logger.error(f"Failed to add label 'jules' to issue #{issue_num} in {repo}: {e}")


# Maintain backwards compatibility
JulesFeedbackDaemon = AutonomousTriageDaemon


if __name__ == "__main__":
    try:
        daemon = AutonomousTriageDaemon()
        daemon.run_triage()
    except Exception as exc:
        logger.error(f"Daemon crashed: {exc}")
        sys.exit(1)
