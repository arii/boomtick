import json
import subprocess

out = subprocess.check_output(['gh', 'pr', 'list', '--state', 'open', '--json', 'number,title,body,statusCheckRollup'])
data = json.loads(out)
for pr in data:
    status_checks = pr.get('statusCheckRollup', [])
    if status_checks:
        all_passed = all(check.get('conclusion') in ('SUCCESS', 'SKIPPED') for check in status_checks)
        status = "SUCCESS" if all_passed else "FAILURE"
    else:
        status = "PENDING"

    fixes_line = [line for line in pr.get('body', '').split('\n') if "Fixes #" in line]
    fixes = fixes_line[0] if fixes_line else "None"

    print(f"PR #{pr['number']}: {pr['title']} - Status: {status} - Fixes: {fixes}")
