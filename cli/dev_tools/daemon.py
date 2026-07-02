import sys
import logging
from dev_tools.services.jules import JulesClient
from dev_tools.services.github import GitHubClient
from dev_tools.orchestrator import Orchestrator
from typing import Dict, Any, Optional, List
import time
import json
import re
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ExtendedJulesClient(JulesClient):
    """JulesClient subclass with extended timeouts for daemon use."""
    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        clean_id = self._get_clean_id(session_id, "sessions")
        url = f"{self.base_url}/sessions/{clean_id}/activities"
        # Set timeout to 30s instead of the default 10s
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        activities = response.json().get("activities", [])
        messages = []
        for act in activities:
            content = self._extract_activity_content(act)
            if content:
                messages.append({
                    "role": "user" if act.get("originator") == "user" else "jules",
                    "content": content,
                    "time": act.get("createTime")
                })
        return messages


class JulesFeedbackDaemon:
    def __init__(self):
        self.jules = ExtendedJulesClient()
        self.github = GitHubClient()
        self.orchestrator = Orchestrator()
        # Ensure the orchestrator uses our extended client
        self.orchestrator.jules = self.jules

    def run(self):
        logger.info("Starting Jules Feedback Daemon")
        try:
            sessions = self.jules.list_sessions(pageSize=50)
            logger.info(f"Found {len(sessions)} sessions")

            open_prs = self.github.list_pull_requests(state="open")
            logger.info(f"Found {len(open_prs)} open PRs")
        except Exception as e:
            logger.error(f"Error fetching initial data: {e}")
            sys.exit(1)

        # Pre-process PRs for faster lookup
        pr_map = {}
        for pr in open_prs:
            pr_title = pr.get("title", "") or ""
            pr_body = pr.get("body", "") or ""
            pr_branch = pr.get("headRefName", "") or ""
            pr_map[pr['number']] = {
                'title': pr_title.lower(),
                'body': pr_body,
                'branch': pr_branch,
                'raw': pr
            }

        for session in sessions:
            self._process_session(session, pr_map)

    def _process_session(self, session: Dict[str, Any], pr_map: Dict[int, Dict[str, Any]]):
        session_id = session.get("name", "").replace("sessions/", "")
        if not session_id:
            return

        logger.info(f"Processing session {session_id}")
        prompt = session.get("prompt", "")
        prompt_lower = prompt.lower()

        matched_pr = None
        for pr_number, pr_data in pr_map.items():
            # Match by session ID in PR body using regex to ensure word boundaries
            # or simply just finding it since it's a very long unique ID
            if session_id in pr_data['body']:
                matched_pr = pr_data['raw']
                break

            # Match by PR branch name in prompt
            if pr_data['branch'] and pr_data['branch'] in prompt:
                matched_pr = pr_data['raw']
                break

            # Try matching PR title as a substring of prompt or vice-versa
            if pr_data['title'] and (pr_data['title'] in prompt_lower or prompt_lower in pr_data['title']):
                matched_pr = pr_data['raw']
                break

        if not matched_pr:
            logger.info(f"No matching PR found for session {session_id}")
            return

        logger.info(f"Matched PR #{matched_pr['number']} ({matched_pr.get('headRefName')}) for session {session_id}")

        try:
            messages = self.jules.get_messages(session_id)
        except Exception as e:
            logger.error(f"Error getting messages for session {session_id}: {e}")
            return

        if not messages:
            logger.info(f"No messages for session {session_id}")
            return

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

if __name__ == '__main__':
    try:
        daemon = JulesFeedbackDaemon()
        daemon.run()
    except Exception as e:
        logger.error(f"Daemon crashed: {e}")
        sys.exit(1)
