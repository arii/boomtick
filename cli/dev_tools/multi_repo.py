"""Multi-repository ecosystem discovery, context synchronization, and sequential execution."""

# pylint: disable=too-many-branches,too-many-locals,too-many-statements

import json
import pathlib
import re
import subprocess
import time
from typing import Any, Dict, List, Optional


def discover_ecosystem_repos(
    root_dir: Optional[pathlib.Path] = None,
    explicit_config: Optional[Any] = None,
    filter_repos: Optional[List[str]] = None,
) -> Dict[str, pathlib.Path]:
    """
    Discovers repositories in the ecosystem based on:
    1. Explicit 'ecosystem_repos' in project_config.json (or passed as explicit_config)
    2. Sibling directory auto-discovery under the repository's parent directory.
    """
    if root_dir is None:
        root_dir = pathlib.Path.cwd().resolve()
    else:
        root_dir = pathlib.Path(root_dir).resolve()

    discovered: Dict[str, pathlib.Path] = {}

    # 1. Determine current repository name
    current_name = _get_repo_name_from_dir(root_dir)
    discovered[current_name] = root_dir

    # 2. Check explicit configuration
    config_data = explicit_config
    if config_data is None:
        config_path = root_dir / "project_config.json"
        if config_path.exists():
            try:
                config_data = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                config_data = {}

    has_explicit_eco = False
    if isinstance(config_data, dict):
        eco = config_data.get("ecosystem_repos")
        if isinstance(eco, dict):
            has_explicit_eco = True
            for name, path_str in eco.items():
                p = (root_dir / path_str).resolve()
                if p.exists() and p.is_dir():
                    discovered[name] = p
        elif isinstance(eco, list):
            has_explicit_eco = True
            for item in eco:
                p = (root_dir / item).resolve()
                if p.exists() and p.is_dir():
                    name = _get_repo_name_from_dir(p)
                    discovered[name] = p

    # 3. Sibling directory auto-discovery (if no explicit config, or for discovery)
    if not has_explicit_eco:
        parent = root_dir.parent
        if parent.exists() and parent.is_dir():
            for sibling in sorted(parent.iterdir()):
                if not sibling.is_dir():
                    continue
                if sibling.name.startswith(".") or sibling.name in ("node_modules", ".venv", "dist"):
                    continue
                # Skip transient worktree / baseline directories
                if sibling.name.endswith("-baseline") or sibling.name.endswith("-worktree"):
                    continue

                # A valid repository candidate has a .git directory and project_config.json or package.json
                if (sibling / ".git").exists() and (
                    (sibling / "project_config.json").exists() or (sibling / "package.json").exists()
                ):
                    sibling_name = _get_repo_name_from_dir(sibling)
                    if sibling_name not in discovered:
                        discovered[sibling_name] = sibling

    # Filter if requested
    if filter_repos:
        norm_filters = [f.lower().strip() for f in filter_repos]
        filtered = {}
        for name, p in discovered.items():
            for f in norm_filters:
                if f == name.lower() or f == p.name.lower() or f in name.lower():
                    filtered[name] = p
                    break
        return filtered

    return discovered


def _get_repo_name_from_dir(d: pathlib.Path) -> str:
    """Extracts canonical repository name from project_config.json, git remote, or folder name."""
    cfg = d / "project_config.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            if data.get("github_repo"):
                return str(data["github_repo"])
            if data.get("packageName"):
                return str(data["packageName"])
        except Exception:
            pass

    pkg = d / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            if data.get("name"):
                return str(data["name"])
        except Exception:
            pass

    try:
        res = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=str(d),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            url = res.stdout.strip()
            match = re.search(r"[:/]([^/]+/[^/.]+)(\.git)?$", url)
            if match:
                return match.group(1)
    except Exception:
        pass

    return d.name


def get_repo_summary(repo_name: str, repo_path: pathlib.Path) -> Dict[str, Any]:
    """Returns runtime, git, and context status for a repository."""
    branch = "unknown"
    commit = "unknown"
    is_dirty = False

    try:
        res_b = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if res_b.returncode == 0:
            branch = res_b.stdout.strip()

        res_c = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if res_c.returncode == 0:
            commit = res_c.stdout.strip()

        res_s = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if res_s.returncode == 0:
            is_dirty = bool(res_s.stdout.strip())
    except Exception:
        pass

    context_file = repo_path / ".agent-context.json"
    has_context = context_file.exists()

    config_info = {}
    config_path = repo_path / "project_config.json"
    if config_path.exists():
        try:
            config_info = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "repo": repo_name,
        "path": str(repo_path),
        "branch": branch,
        "commit": commit,
        "is_dirty": is_dirty,
        "has_context": has_context,
        "config": config_info,
    }


def exec_in_repos(
    repos: Dict[str, pathlib.Path],
    command: str,
    continue_on_error: bool = True,
) -> Dict[str, Any]:
    """
    Executes a shell command sequentially across a set of repositories.
    """
    results: List[Dict[str, Any]] = []
    total_failed = 0
    total_passed = 0

    for name, path in repos.items():
        start_time = time.time()
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(path),
                capture_output=True,
                text=True,
                check=False,
            )
            duration = round(time.time() - start_time, 2)
            passed = proc.returncode == 0

            if passed:
                total_passed += 1
            else:
                total_failed += 1

            results.append(
                {
                    "repo": name,
                    "path": str(path),
                    "command": command,
                    "exit_code": proc.returncode,
                    "passed": passed,
                    "duration_seconds": duration,
                    "stdout": proc.stdout.strip(),
                    "stderr": proc.stderr.strip(),
                }
            )

            if not passed and not continue_on_error:
                break

        except Exception as e:
            duration = round(time.time() - start_time, 2)
            total_failed += 1
            results.append(
                {
                    "repo": name,
                    "path": str(path),
                    "command": command,
                    "exit_code": -1,
                    "passed": False,
                    "duration_seconds": duration,
                    "stdout": "",
                    "stderr": str(e),
                }
            )
            if not continue_on_error:
                break

    return {
        "status": "success" if total_failed == 0 else ("partial_success" if total_passed > 0 else "error"),
        "total_repos": len(repos),
        "total_passed": total_passed,
        "total_failed": total_failed,
        "results": results,
    }


def warm_ecosystem_context(
    repos: Dict[str, pathlib.Path],
    force: bool = False,
) -> Dict[str, Any]:
    """
    Warms/updates .agent-context.json across all discovered repositories.
    Prefers 'pnpm run agent:prime' if available in package.json, otherwise runs 'td context-warm'.
    """
    results: List[Dict[str, Any]] = []
    total_failed = 0
    total_passed = 0

    for name, path in repos.items():
        has_agent_prime = False
        pkg = path / "package.json"
        if pkg.exists():
            try:
                pkg_data = json.loads(pkg.read_text(encoding="utf-8"))
                has_agent_prime = "agent:prime" in pkg_data.get("scripts", {})
            except Exception:
                pass

        if has_agent_prime:
            cmd = "pnpm run agent:prime"
        else:
            force_flag = " --force" if force else ""
            cmd = f"td context-warm{force_flag}"

        start_time = time.time()
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(path),
            capture_output=True,
            text=True,
            check=False,
        )
        duration = round(time.time() - start_time, 2)
        passed = proc.returncode == 0
        if passed:
            total_passed += 1
        else:
            total_failed += 1

        results.append(
            {
                "repo": name,
                "path": str(path),
                "strategy": "pnpm run agent:prime" if has_agent_prime else "td context-warm",
                "exit_code": proc.returncode,
                "passed": passed,
                "duration_seconds": duration,
                "output": proc.stdout.strip() or proc.stderr.strip(),
            }
        )

    return {
        "status": "success" if total_failed == 0 else "error",
        "total_repos": len(repos),
        "total_passed": total_passed,
        "total_failed": total_failed,
        "results": results,
    }
