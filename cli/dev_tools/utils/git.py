"""Git utilities for secure branch operations."""
import os
import re
import subprocess
from typing import Optional
from dev_tools.utils import CLIError, log_warn, mask_sensitive_data

class GitUtility:  # pylint: disable=too-few-public-methods
    """Utility class for Git operations."""

    def __init__(self, token: Optional[str] = None, repo: Optional[str] = None):
        self.token = token
        self.repo = repo

    def branch_exists_locally(self, branch: str) -> bool:
        """Checks if a branch exists in the local repository."""
        proc = subprocess.run(
            ["git", "show-ref", "--verify", f"refs/heads/{branch}"],
            capture_output=True,
            text=True,
            check=False
        )
        return proc.returncode == 0

    def push_branch(self, branch: str) -> bool:
        """Securely pushes a local branch to the remote origin."""
        # Security: Validate branch name to prevent injection
        if not re.match(r"^[a-zA-Z0-9._/-]+$", branch):
            raise CLIError(f"Invalid branch name: {branch}", code=400)

        try:
            # Check if branch exists locally
            if not self.branch_exists_locally(branch):
                log_warn(f"Local branch '{branch}' not found. Cannot push.")
                return False

            log_warn(f"Pushing local branch '{branch}' to origin...")

            # Security: Use environment variable for token to avoid leaking in process list
            env = os.environ.copy()
            if self.token and self.repo:
                env["GIT_TOKEN_FOR_PUSH"] = self.token
                # Use a credential helper to pass the token securely
                cred_helper = "!f() { echo \"username=x-access-token\"; echo \"password=$GIT_TOKEN_FOR_PUSH\"; }; f"
                push_url = f"https://github.com/{self.repo}.git"
                push_args = ["git", "-c", f"credential.helper={cred_helper}", "push", "-u", push_url, branch]
            else:
                push_args = ["git", "push", "-u", "origin", branch]

            # Capture output and handle error manually to avoid leaking sensitive info in exceptions
            push_res = subprocess.run(
                push_args,
                capture_output=True,
                text=True,
                env=env,
                check=False
            )

            if push_res.returncode != 0:
                sanitized_stderr = mask_sensitive_data(push_res.stderr)
                log_warn(f"Failed to push branch '{branch}': {sanitized_stderr}")
                return False

            return True

        except (subprocess.SubprocessError, OSError) as e:
            log_warn(f"Unexpected error during git push for branch '{branch}': {mask_sensitive_data(str(e))}")
            return False
