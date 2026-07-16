import json
import glob

def find_errors():
    verdict_files = glob.glob("collected-logs/**/*-verdict.json", recursive=True)
    failures = []

    for vf in verdict_files:
        with open(vf, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                if data.get('verdict') != 'pass' and data.get('verdict') != 'approve':
                     failures.append({
                         "file": vf,
                         "verdict": data.get('verdict'),
                         "reason": data.get('reason', 'unknown')
                     })
            except:
                pass

    print(f"Found {len(failures)} failures/non-pass verdicts.")
    for f in failures[:5]:
         print(f)

find_errors()
