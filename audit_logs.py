import os
import json
import glob

def find_md_files(directory):
    md_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith("code-review.md"):
                md_files.append(os.path.join(root, file))
    return md_files

def extract_prompt_verdict(md_file):
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Simple heuristic to extract prompt and verdict, assuming some structure
    # You might need to adjust this depending on the exact structure of the markdown files
    if "Prompt:" in content and "Verdict:" in content:
        prompt_start = content.find("Prompt:")
        verdict_start = content.find("Verdict:")
        return content[prompt_start:verdict_start].strip(), content[verdict_start:].strip()
    return None, None

def analyze_logs(base_dir):
    md_files = find_md_files(base_dir)
    findings = []

    for file in md_files:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Example issues to look for
        if "hallucin" in content.lower() or "not found" in content.lower() or "error" in content.lower():
             findings.append(f"Potential issue found in {file}")

        # Just grab the full verdict json if possible
        verdict_file = file.replace(".md", "-verdict.json")
        if os.path.exists(verdict_file):
             try:
                 with open(verdict_file, 'r') as vf:
                     vdata = json.load(vf)
                     # check for issues in verdict
                     if vdata.get("status") != "success":
                         pass # handle non success
             except:
                 pass

    return findings

if __name__ == "__main__":
    findings = analyze_logs("./collected-logs")
    for f in findings:
        print(f)
