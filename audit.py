import subprocess
import json

def get_issue(num):
    res = subprocess.run(f"td-cli gh issue-view {num}", shell=True, capture_output=True, text=True)
    return res.stdout

def search_issues():
    res = subprocess.run(f"td-cli gh validate-issue --all-open", shell=True, capture_output=True, text=True)
    return res.stdout

print(search_issues())
