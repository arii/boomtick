# pylint: disable=missing-docstring,too-many-branches
import os
import re
import subprocess
import sys


def check_shell_script(filepath):
    """Performs static analysis on a shell script."""
    findings = []

    # 1. Syntax check (only for .sh files)
    if filepath.endswith(".sh"):
        try:
            subprocess.run(["bash", "-n", filepath], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            findings.append(f"Syntax error: {e.stderr.strip()}")
            return findings

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        findings.append(f"Could not read file: {e}")
        return findings

    # 2. Missing error handling in scripts (check first 10 lines for set -e, set -u, set -o pipefail)
    uncommented_first_lines = [re.sub(r"#.*", "", line) for line in lines[:10]]
    settings_content = " ".join(uncommented_first_lines)

    missing_settings = []
    if not re.search(r"set\s+-[^ \n]*e", settings_content):
        missing_settings.append("set -e (errexit)")
    if not re.search(r"set\s+-[^ \n]*u", settings_content):
        missing_settings.append("set -u (nounset)")
    if "pipefail" not in settings_content:
        missing_settings.append("set -o pipefail")

    if missing_settings and len(lines) > 5:
        findings.append(f"Script lacks recommended settings in first 10 lines: {', '.join(missing_settings)}")

    # 3. Pattern checks
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Hardcoded absolute paths (excluding common system ones)
        if re.search(
            r'(^|\s|["\'])/(?!(bin|usr/bin|dev|proc|tmp|etc|lib|var/lib|sys|usr/sbin|sbin|var/run))[a-zA-Z0-9]',
            line,
        ):
            if not re.search(r"[0-9]\s*/\s*[0-9]", line):  # Avoid flagging division
                findings.append(f"Line {i+1}: Potential hardcoded absolute path: {stripped}")

        # Unquoted variables in risky commands - SIMPLIFIED heuristic
        # We flag cases where a variable expansion ($VAR or ${VAR}) is used in a risky command
        # without any quotes on that line. This is a simple signal.
        if any(cmd in stripped for cmd in ["rm ", "cp ", "mv ", "ls "]):
            if "$" in stripped and not any(q in stripped for q in ['"', "'"]):
                findings.append(f"Line {i+1}: Potential unquoted variable in risky command: {stripped}")

    if len(lines) > 20:
        findings.append("Note: For complex shell scripts, please run 'shellcheck' for deeper analysis.")

    return findings


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 verify_infra.py <filepath>")
        sys.exit(1)

    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)

    findings = check_shell_script(filepath)
    if findings:
        print(f"Infrastructure violations found in {filepath}:")
        for f in findings:
            print(f"- {f}")
        sys.exit(1)
    else:
        print(f"No infrastructure violations found in {filepath}.")
        sys.exit(0)


if __name__ == "__main__":
    main()
