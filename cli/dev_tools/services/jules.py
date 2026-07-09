import os
import sys
import requests
from dev_tools.utils import log_warn, log_debug, log_info
from typing import Optional, List, Dict, Any, Union
from concurrent.futures import ThreadPoolExecutor, as_completed

class JulesClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("JULES_API_KEY")
        if not self.api_key:
            raise ValueError("JULES_API_KEY is not set or empty")

        self.base_url = "https://jules.googleapis.com/v1alpha"
        self.legacy_url = "https://api.jules.ai/v1/sessions"
        self.headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }

    def _get_clean_id(self, res_id: str, prefix: str) -> str:
        return res_id.replace(f"{prefix}/", "")

    def list_sources(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/sources"
        response = requests.get(url, headers=self.headers, timeout=10)
        response.raise_for_status()
        return response.json().get("sources", [])

    def list_sessions(self, pageSize: int = 100) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/sessions"
        params = {"pageSize": pageSize}
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json().get("sessions", [])

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        clean_id = self._get_clean_id(session_id, "sessions")
        url = f"{self.base_url}/sessions/{clean_id}"
        response = requests.get(url, headers=self.headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def discover_source_id(self, repo_full_name: str) -> Optional[str]:
        sources = self.list_sources()
        for s in sources:
            ctx = s.get("githubRepo", {})
            owner, repo = ctx.get("owner"), ctx.get("repo")
            if owner and repo and f"{owner}/{repo}" == repo_full_name:
                return self._get_clean_id(s.get("name") or "", "sources")
            if repo_full_name in s.get("displayName", ""):
                return self._get_clean_id(s.get("name") or "", "sources")
        return None

    def create_session_from_source(self, source_id: str, branch: str, prompt: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/sessions"
        clean_source_id = self._get_clean_id(source_id, "sources")
        payload = {
            "prompt": prompt,
            "sourceContext": {
                "source": f"sources/{clean_source_id}",
                "githubRepoContext": { "startingBranch": branch }
            },
            "automationMode": "AUTO_CREATE_PR"
        }

        log_debug(f"Creating Jules session at {url}")
        log_debug(f"Payload: {payload}")

        response = requests.post(url, headers=self.headers, json=payload, timeout=15)
        response.raise_for_status()
        return response.json()

    def create_session(self, prompt: str, branch: str, title: str, owner: str, repo_name: str) -> str:
        """Creates a new Jules session via the legacy API."""
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"prompt": prompt, "branch": branch, "title": title, "owner": owner, "repo_name": repo_name}
        try:
            response = requests.post(self.legacy_url, headers=headers, json=payload)
            response.raise_for_status()
            session_id = response.json().get("id")
            if not session_id:
                raise RuntimeError("Could not find session ID in API response.")
            return session_id
        except requests.exceptions.RequestException as e:
            error_msg = f"Error creating Jules session: {e}"
            if e.response is not None:
                error_msg += f"\nResponse: {e.response.text}"
            raise RuntimeError(error_msg)

    def _extract_activity_content(self, act: Dict[str, Any]) -> str:
        if act.get("userMessaged"):
            um = act["userMessaged"]
            if isinstance(um, str): return um
            if isinstance(um, dict):
                user_msg = um.get("userMessage", "")
                return user_msg.get("body", "") if isinstance(user_msg, dict) else user_msg
        elif act.get("progressUpdated") and isinstance(act["progressUpdated"], dict):
            return act["progressUpdated"].get("description", "")
        elif act.get("planGenerated") and isinstance(act["planGenerated"], dict):
            plan = act["planGenerated"].get("plan") or {}
            steps = plan.get("steps", []) if isinstance(plan, dict) else []
            return "Generated plan:\n" + "\n".join(f"- {s.get('description', '')}" for s in steps if isinstance(s, dict))
        elif act.get("sessionCompleted"):
            return "Session completed successfully."
        return ""

    def get_messages(self, session_id: str, timeout: int = 10) -> List[Dict[str, Any]]:
        clean_id = self._get_clean_id(session_id, "sessions")
        url = f"{self.base_url}/sessions/{clean_id}/activities"
        response = requests.get(url, headers=self.headers, timeout=timeout)
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

    def send_message(self, session_id: Union[str, List[str]], message: str) -> Dict[str, Any]:
        session_ids = [session_id] if isinstance(session_id, str) else session_id

        if len(session_ids) == 1:
            return self._send_single_message(session_ids[0], message)

        # The Pydantic model now enforces the BATCH_CAP, but we keep this as a secondary safety
        BATCH_CAP = 50
        if len(session_ids) > BATCH_CAP:
            log_warn(f"Batch size {len(session_ids)} exceeds cap of {BATCH_CAP}. Truncating.")
            session_ids = session_ids[:BATCH_CAP]

        log_info(f"Batch sending message to {len(session_ids)} sessions...")

        results = []
        with ThreadPoolExecutor(max_workers=min(len(session_ids), 10)) as executor:
            # Submit all tasks and keep track of futures in order
            futures = [executor.submit(self._send_single_message, sid, message) for sid in session_ids]

            # Reconstruct results in the original input order by iterating over the futures list
            for sid, future in zip(session_ids, futures):
                try:
                    res = future.result()
                    results.append({"sessionId": sid, "status": "success"})
                except Exception as exc:
                    log_warn(f"Failed to send message to {sid}: {exc}")
                    results.append({"sessionId": sid, "status": "error", "message": str(exc)})

        return {
            "status": "success" if any(r["status"] == "success" for r in results) else "error",
            "message": f"Batch send completed. {sum(1 for r in results if r['status'] == 'success')}/{len(session_ids)} successful.",
            "results": results
        }

    def _send_single_message(self, session_id: str, message: str) -> Dict[str, Any]:
        clean_id = self._get_clean_id(session_id, "sessions")
        url = f"{self.base_url}/sessions/{clean_id}:sendMessage"
        response = requests.post(url, headers=self.headers, json={"prompt": message}, timeout=10)
        response.raise_for_status()
        return {"status": "success", "message": "Message sent successfully"}

    def cancel_session(self, session_id: str) -> Dict[str, Any]:
        clean_id = self._get_clean_id(session_id, "sessions")
        url = f"{self.base_url}/sessions/{clean_id}"
        response = requests.delete(url, headers=self.headers, timeout=10)
        response.raise_for_status()
        return {"status": "success", "message": "Session cancelled successfully"}
