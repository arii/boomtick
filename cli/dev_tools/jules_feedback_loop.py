#!/usr/bin/env python3
import sys
import os
import json
import time

# Ensure imports work regardless of execution directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tdw_services.services.jules import JulesClient
from tdw_services.services.github import GitHubClient
from utils import clean_gha_logs, extract_failing_info


def main():
    print("🚀 Starting Jules Auto-Feedback Daemon...")

    try:
        jules_client = JulesClient()
        gh_client = GitHubClient()
    except Exception as e:
        print(f"❌ Initialization Error: {e}")
        return

    print("Fetching active Jules sessions...")
    sessions = jules_client.list_sessions(pageSize=50)
    print(f"Found {len(sessions)} sessions.")

    repo = gh_client.repo
    print(f"Fetching open PRs for repo {repo}...")
    try:
        open_prs = gh_client._request('GET', f'/repos/{repo}/pulls?state=open')
        print(f"Found {len(open_prs)} open PRs.")
    except Exception as e:
        print(f"❌ Error fetching PRs: {e}")
        return

    for session in sessions:
        session_id = session.get('name')
        if not session_id:
            continue

        # Try to match session to a PR
        matched_pr = None
        for pr in open_prs:
            title = pr.get('title', '')
            body = pr.get('body', '')
            branch = pr.get('head', {}).get('ref', '')

            clean_sid = session_id.replace("sessions/", "")

            if clean_sid in title or clean_sid in body:
                matched_pr = pr
                break

            prompt = session.get("prompt", "")
            if branch and branch in prompt:
                matched_pr = pr
                break

        if not matched_pr:
            continue

        print(f"🔗 Matched Session {session_id} to PR #{matched_pr.get('number')} ({matched_pr.get('title')})")

        # Check message history to ensure the agent is waiting for feedback
        messages = jules_client.get_messages(session_id)
        if not messages:
            print(f"  No messages found for session {session_id}, skipping.")
            continue

        last_message = messages[-1]
        if last_message.get("role") != "jules":
            print(f"  Last message is from '{last_message.get('role')}' (not jules), skipping to avoid loop.")
            continue

        print(f"  Agent is waiting for feedback. Checking CI status...")

        commit_sha = matched_pr.get('head', {}).get('sha')
        if not commit_sha:
            print(f"  No head SHA found for PR #{matched_pr.get('number')}, skipping.")
            continue

        check_runs = gh_client.fetch_check_runs(commit_sha)

        if not check_runs:
            print(f"  No check runs found for PR #{matched_pr.get('number')}.")
            continue


        all_passed = True
        failed_checks = []

        for run in check_runs:
            status = run.get('status')
            conclusion = run.get('conclusion')

            if status != 'completed':
                print(f"  Check '{run.get('name')}' is still {status}, skipping feedback for now.")
                all_passed = False
                break

            if conclusion == 'failure':
                all_passed = False
                failed_checks.append(run)

        # If checks are still running, we skip (handled above)
        # If checks failed, we send failure logs
        if failed_checks:
            feedback = "The CI pipeline reported failures. Here are the details:\n\n"
            for run in failed_checks:
                run_id = run.get('id')
                name = run.get('name')
                external_id = run.get('external_id')

                print(f"  Fetching logs for failed check: {name} (ID: {run_id})")
                logs = gh_client.fetch_check_run_logs(run_id, external_id)

                clean_logs = clean_gha_logs(logs)
                extracted_info = extract_failing_info(clean_logs)

                feedback += f"### Failed Check: {name}\n"
                if extracted_info:
                    for info in extracted_info:
                        feedback += f"- File: `{info['file']}:{info['line']}` ({info['type']})\n  Message: {info['message']}\n"
                else:
                    # Provide snippet of cleaned logs if extraction didn't catch it
                    lines = clean_logs.splitlines()
                    snippet = "\n".join(lines[-30:]) if lines else "No logs found."
                    feedback += f"```\n{snippet}\n```\n"

            print(f"  Sending failure feedback to session {session_id}...")
            jules_client.send_message(session_id, feedback)
            print("  Feedback sent.")

        elif all_passed and check_runs:
            print(f"  All checks passed for session {session_id}. Sending success feedback...")
            jules_client.send_message(session_id, "All checks passed successfully. You may proceed.")
            print("  Success feedback sent.")

if __name__ == "__main__":
    main()
