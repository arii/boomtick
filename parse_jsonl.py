import json
import glob

def parse_logs():
    all_jsonl = glob.glob("collected-logs/**/logs/ai/*.jsonl", recursive=True)
    findings = []

    # We are specifically looking for issues where AI review quota was met or any other failure that the agent mentions.
    # In earlier run, we found "Skipped: review quota (10) already met." in the MD files. Let's trace it.

    md_files = glob.glob("collected-logs/**/*.md", recursive=True)
    quota_met_count = 0
    quota_met_runs = set()

    for mf in md_files:
        with open(mf, 'r', encoding='utf-8') as f:
            content = f.read()
            if "Skipped: review quota" in content:
                quota_met_count += 1
                run_dir = mf.split('/')[1]
                quota_met_runs.add(run_dir)

    print(f"Quota met found in {quota_met_count} markdown files across {len(quota_met_runs)} runs.")
    if len(quota_met_runs) > 0:
        print("Example runs with quota met:")
        for r in list(quota_met_runs)[:5]:
            print(f" - {r}")

parse_logs()
