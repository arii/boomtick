#!/usr/bin/env python3
# This script statically verifies that any GitHub Actions workflow utilizing
# `docker/build-push-action` with cache export (`cache-to: type=gha`) is preceded
# by Buildx setup or our custom setup-docker-buildx action in the same job context.
#
# It enforces compliance with repository policies regarding Docker caching.

import os
import sys
import re

def verify_workflows():
    workflow_dir = ".github/workflows"
    if not os.path.exists(workflow_dir):
        print(f"Directory {workflow_dir} not found.")
        return 0

    violations = []

    # Search for all .yml and .yaml files in .github/workflows/
    for filename in os.listdir(workflow_dir):
        if not (filename.endswith(".yml") or filename.endswith(".yaml")):
            continue

        file_path = os.path.join(workflow_dir, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            file_violations = check_workflow_file(file_path, content)
            violations.extend(file_violations)
        except Exception as e:
            violations.append(f"Error reading {file_path}: {e}")

    if violations:
        print("❌ Workflow compliance audit failed with the following violations:\n")
        for v in violations:
            print(v)
        return 1
    else:
        print("✅ All workflows are compliant with Buildx setup requirements.")
        return 0

def check_workflow_file(file_path, content):
    violations = []
    lines = content.splitlines()

    in_jobs_block = False
    current_job_name = None
    job_indentation = -1

    current_job_steps = []
    current_step_lines = []

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indentation = len(line) - len(line.lstrip())

        # Detect jobs block
        if stripped.startswith("jobs:"):
            in_jobs_block = True
            job_indentation = indentation
            continue

        if in_jobs_block:
            # If indentation is less than or equal to jobs: indentation, we are out of jobs block
            if indentation <= job_indentation and not stripped.startswith("jobs:"):
                # Close the previous job
                if current_job_name:
                    if current_step_lines:
                        current_job_steps.append((current_step_lines, idx - len(current_step_lines)))
                    violations.extend(verify_job_steps(file_path, current_job_name, current_job_steps))
                in_jobs_block = False
                current_job_name = None
                current_job_steps = []
                current_step_lines = []
                continue

            # Detect a job key.
            # In standard workflows, it's indented by 2 spaces.
            # We also ensure we don't treat keys inside steps or step `with` block as a job name.
            is_job_key = (indentation > job_indentation and
                          stripped.endswith(":") and
                          not stripped.startswith("-") and
                          not re.match(r"^(with|env|steps|outputs|runs-on|strategy|needs|if|permissions|concurrency):", stripped))

            if is_job_key and (indentation == job_indentation + 2 or not current_job_name):
                # Close the previous job
                if current_job_name:
                    if current_step_lines:
                        current_job_steps.append((current_step_lines, idx - len(current_step_lines)))
                    violations.extend(verify_job_steps(file_path, current_job_name, current_job_steps))

                current_job_name = stripped[:-1].strip()
                current_job_steps = []
                current_step_lines = []
                continue

            # If we are inside a job, detect steps
            if current_job_name:
                # If a line starts with `-`, it indicates a new step
                if stripped.startswith("-"):
                    if current_step_lines:
                        current_job_steps.append((current_step_lines, idx - len(current_step_lines)))
                    current_step_lines = [line]
                else:
                    if current_step_lines:
                        current_step_lines.append(line)

    # Close final job
    if current_job_name:
        if current_step_lines:
            current_job_steps.append((current_step_lines, len(lines) - len(current_step_lines) + 1))
        violations.extend(verify_job_steps(file_path, current_job_name, current_job_steps))

    return violations

def verify_job_steps(file_path, job_name, steps):
    violations = []
    buildx_setup_seen = False

    for idx, (step_lines, step_start_line) in enumerate(steps, 1):
        step_content = "\n".join(step_lines)

        # Check if the step uses setup-buildx or setup-docker-buildx
        uses_match = re.search(r"uses:\s*(\S+)", step_content)
        if uses_match:
            action_name = uses_match.group(1).strip("'\"")
            if "docker/setup-buildx-action" in action_name or "setup-docker-buildx" in action_name:
                buildx_setup_seen = True

        # Check if the step uses docker/build-push-action
        if uses_match and "docker/build-push-action" in uses_match.group(1):
            # Check if cache-to: type=gha is configured
            cache_to_match = re.search(r"cache-to\s*:\s*(\S.*)", step_content)
            if cache_to_match:
                cache_to_val = cache_to_match.group(1)
                if "type=gha" in cache_to_val or "type=gha" in step_content:
                    if not buildx_setup_seen:
                        violations.append(
                            f"❌ Violation in '{file_path}' in job '{job_name}' near line {step_start_line}:\n"
                            f"  Step using `docker/build-push-action` exports GHA cache (`cache-to: type=gha`),\n"
                            f"  but is not preceded by `docker/setup-buildx-action` or custom composite `.github/actions/setup-docker-buildx` action."
                        )

    return violations

if __name__ == "__main__":
    sys.exit(verify_workflows())
