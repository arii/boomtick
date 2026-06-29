#!/usr/bin/env python3
import sys
import os
import json
import time
import subprocess
import re

from tdw_services.services.jules import JulesClient
from tdw_services.services.github import GitHubClient
from dev_tools.utils import clean_gha_logs, extract_failing_info


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

        # Generate initial feedback based on CI status
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
        elif all_passed and check_runs:
            feedback = "All checks passed successfully. You may proceed.\n\n"
        else:
            feedback = ""

        # Perform full dev-tools pipeline: Audit, AI Review, UX Report
        pr_num = matched_pr.get('number')
        if not isinstance(pr_num, int) or pr_num <= 0:
            print(f"  Invalid PR number {pr_num}, skipping.")
            continue

        print(f"  Running dev-tools pipeline for PR #{pr_num}...")
        try:
            env = os.environ.copy()
            # Ensure PYTHONPATH includes the cli root for td_cli.py
            cli_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            env["PYTHONPATH"] = f"{cli_root}:{env.get('PYTHONPATH', '')}"
            td_cli_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "td_cli.py")
            pr_num_str = str(pr_num)

            # 1. Heuristic Code Audit
            print(f"    - Running Heuristic Audit...")
            audit_res = subprocess.run(
                [sys.executable, td_cli_path, "gh", "audit-pr", pr_num_str, "--fetch", "--audit"],
                capture_output=True, text=True, env=env
            )
            if audit_res.returncode == 0:
                try:
                    audit_data = json.loads(audit_res.stdout)
                    auto_findings = audit_data.get("auto_findings", [])
                    if auto_findings:
                        feedback += f"## Heuristic Audit Findings\n"
                        for finding in auto_findings:
                            feedback += f"- **{finding.get('severity', 'info')}** ({finding.get('path')}): {finding.get('issue')}\n"
                        feedback += "\n"
                except json.JSONDecodeError as e:
                    feedback += f"## Heuristic Audit Findings\nFailed to parse JSON output: {e}\n\n"

            # 2. AI Code Review
            print(f"    - Running AI Code Review...")
            review_res = subprocess.run(
                [sys.executable, td_cli_path, "ai", "review", pr_num_str],
                capture_output=True, text=True, env=env
            )
            if review_res.returncode == 0:
                try:
                    review_data = json.loads(review_res.stdout)
                    feedback += f"## Automated Code Review\n{review_data.get('reviewComment', '')}\n"
                    if review_data.get('recommendation'):
                        feedback += f"**Recommendation:** {review_data.get('recommendation')}\n\n"
                except json.JSONDecodeError:
                    feedback += f"## Automated Code Review\nFailed to parse JSON output.\n\n"
            else:
                feedback += f"## Automated Code Review\nFailed to run AI review. Return code: {review_res.returncode}\n\n"

            # 3. UX Visual Impact Analysis
            print(f"    - Running UX Report...")
            ux_res = subprocess.run(
                [sys.executable, td_cli_path, "ux", "report"],
                capture_output=True, text=True, env=env
            )
            if ux_res.returncode == 0:
                try:
                    ux_data = json.loads(ux_res.stdout)
                    report_path = ux_data.get("report")
                    if report_path and os.path.exists(report_path):
                        with open(report_path, "r") as f:
                            report_content = f.read()
                        # Extract the key findings summary to avoid spamming the PR
                        match = re.search(r'## Key Findings\n(.*?)(?=\n##|$)', report_content, re.DOTALL)
                        if match:
                            feedback += f"## UX Impact Analysis\n{match.group(1).strip()}\n\n"
                        else:
                            feedback += f"## UX Impact Analysis\nReport generated but no key findings extracted.\n\n"
                except json.JSONDecodeError as e:
                    feedback += f"## UX Impact Analysis\nFailed to parse JSON output: {e}\n\n"

        except Exception as e:
            feedback += f"## Dev-Tools Pipeline Error\nFailed to execute pipeline tasks: {e}\n\n"
            print(f"  Sending error feedback to session {session_id}...")
            jules_client.send_message(session_id, feedback)
            sys.exit(1)

        if not feedback:
            feedback = "No diagnostic information could be generated for this PR."

        print(f"  Sending feedback to session {session_id}...")
        jules_client.send_message(session_id, feedback)
        print("  Feedback sent.")

if __name__ == "__main__":
    main()
