# pylint: disable=arguments-differ,attribute-defined-outside-init,line-too-long,logging-fstring-interpolation,missing-docstring,too-few-public-methods
import logging
import sys
from typing import Any, Dict, List, Optional

from dev_tools.orchestrator import Orchestrator
from dev_tools.services.github import GitHubClient
from dev_tools.services.jules import JulesClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExtendedJulesClient(JulesClient):
    """JulesClient subclass with extended timeouts for daemon use."""

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        # Set timeout to 30s instead of the default 10s
        return super().get_messages(session_id, timeout=30)


class JulesFeedbackDaemon:
    def __init__(self):
        self.jules = ExtendedJulesClient()
        self.github = GitHubClient()
        self.orchestrator = Orchestrator()
        # Ensure the orchestrator uses our extended client
        self.orchestrator.initialize_jules(self.jules)

    def run(self, limit: int = 10):
        logger.info("Starting Jules Feedback Daemon")
        try:
            sessions = self.jules.list_sessions(pageSize=limit)
            logger.info(f"Found {len(sessions)} sessions")
        except Exception as e:
            logger.error(f"Error fetching sessions: {e}")
            sys.exit(1)

        self._pr_cache = {}
        self._session_to_pr_map = {}

        # Batch pre-match sessions to PRs where possible to reduce API hits
        self._pre_match_sessions_batch(sessions)

        for session in sessions:
            self._process_session(session)

    def _pre_match_sessions_batch(self, sessions: List[Dict[str, Any]]):
        """Batch search for multiple session IDs in one GitHub API call."""
        if not sessions:
            return

        session_ids = []
        for s in sessions:
            sid = s.get("name", "").split("/")[-1]
            if sid:
                session_ids.append(sid)

        if not session_ids:
            return

        # GitHub Search API query construction
        # Example: (ID1 OR ID2 OR ID3) in:body,title state:open
        id_query = " OR ".join([f'"{sid}"' for sid in session_ids])
        full_query = f"({id_query}) in:body,title state:open"

        try:
            logger.info(f"Performing batch PR search for {len(session_ids)} session IDs")
            found_prs = self.github.search_pull_requests(full_query, limit=50)

            for pr in found_prs:
                body = (pr.get("body") or "").lower()
                title = (pr.get("title") or "").lower()
                for sid in session_ids:
                    if sid.lower() in body or sid.lower() in title:
                        self._session_to_pr_map[sid] = pr
                        # Cache the PR details as well
                        self._pr_cache[pr["number"]] = pr
        except Exception as e:
            logger.warning(f"Batch PR search failed, will fallback to individual lookups: {e}")

    def _get_pr_for_session(self, session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Optimized PR lookup for a session."""
        session_id = session.get("name", "").replace("sessions/", "")

        # 0. Check batch pre-match results
        if session_id in self._session_to_pr_map:
            return self._session_to_pr_map[session_id]

        # 1-3. Delegate to orchestrator logic
        pr_num = self.orchestrator.get_pr_for_session(session)
        if pr_num:
            if pr_num not in self._pr_cache:
                self._pr_cache[pr_num] = self.github.fetch_pr_details(pr_num)
            return self._pr_cache[pr_num]

        return None

    def _process_session(self, session: Dict[str, Any]):
        session_id = session.get("name", "").replace("sessions/", "")
        if not session_id:
            return

        logger.info(f"Processing session {session_id}")
        matched_pr = self._get_pr_for_session(session)

        if not matched_pr:
            logger.info(f"No matching PR found for session {session_id}")
            return

        try:
            messages = self.jules.get_messages(session_id)
        except Exception as e:
            logger.error(f"Error getting messages for session {session_id}: {e}")
            return

        if not messages:
            logger.info(f"No messages for session {session_id}")
            return

        logger.info(
            f"Matched PR #{matched_pr['number']} ({matched_pr.get('headRefName')}, {matched_pr.get('title')}) for session {session_id}"
        )

        last_message = messages[-1]
        if last_message.get("role") == "user":
            logger.info(f"Last message from user, skipping feedback to avoid double-feedback for {session_id}")
            return

        if last_message.get("role") == "jules":
            logger.info(f"Triggering feedback for session {session_id} matching PR #{matched_pr['number']}")
            try:
                # Use orchestrator.trigger_jules_feedback which executes CI validation logic
                res = self.orchestrator.trigger_jules_feedback(session_id)
                logger.info(f"Feedback triggered successfully: {res.get('status', 'unknown')}")
            except Exception as e:
                logger.error(f"Error triggering feedback for {session_id}: {e}")


if __name__ == "__main__":
    try:
        daemon = JulesFeedbackDaemon()
        daemon.run()
    except Exception as e:
        logger.error(f"Daemon crashed: {e}")
        sys.exit(1)
