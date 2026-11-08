"""Runtime checks, preflight, repair, and workflow compliance."""
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from dev_tools.utils import (
    log_info,
    CLIError,
    get_gha_variable,
    log_error,
    log_warn,
    verify_ci_metrics,
    verify_pr_scope)
from dev_tools.orchestration.quality import QualityMixin
import dev_tools.orchestrator



class RuntimeMixin(QualityMixin):
    """Runtime checks, preflight, repair, and workflow compliance."""

    def runtime_check(self) -> Dict[str, str]:
        """Ensures the runtime environment matches the contract."""
        # NOTE (config-hygiene #1172): single source of truth — .node-version
        # for Node, package.json (packageManager, then engines.pnpm) for pnpm.
        # No hardcoded fallbacks; a missing contract file fails here. This
        # check intentionally mirrors scripts/check-runtime-files.mjs. Kept
        # minimal for the #1177 split — see that issue before restructuring.
        try:
            with open(".node-version", "r", encoding="utf-8") as f:
                expected_node = f.read().strip().replace("v", "")
        except FileNotFoundError:
            raise CLIError("Missing .node-version: it is the single source of truth for the required Node version.")
        if not expected_node:
            raise CLIError("Empty .node-version: it must contain the required Node version.")

        manifest_path = "package.json"
        if not os.path.exists(manifest_path) and os.path.exists("workspace.json"):
            manifest_path = "workspace.json"

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                pkg = json.load(f)
        except FileNotFoundError:
            raise CLIError(
                f"Missing {manifest_path}: it is the single source of truth for the required pnpm version."
            )
        expected_pnpm = pkg.get("packageManager", "").replace("pnpm@", "") or (pkg.get("engines") or {}).get(
            "pnpm", ""
        )
        if not expected_pnpm:
            raise CLIError(f"{manifest_path} must declare the pnpm version via packageManager or engines.pnpm.")

        dev_tools.orchestrator.run_command(["corepack", "enable"], check=False)
        dev_tools.orchestrator.run_command(["corepack", "prepare", f"pnpm@{expected_pnpm}", "--activate"], check=False)

        actual_node_res = dev_tools.orchestrator.run_command(["node", "-v"])
        actual_node = str(actual_node_res).strip().replace("v", "")
        is_ci = os.environ.get("CI") == "true"

        expected_prefix = ".".join(expected_node.split(".")[:2]) + "."
        node_matches = actual_node.startswith(expected_prefix) if is_ci else actual_node == expected_node

        if not node_matches:
            log_error(f"Node version mismatch\nExpected: {expected_node}\nActual:   {actual_node}")
            raise CLIError("Node version mismatch. Do not switch versions manually.")

        actual_pnpm_res = dev_tools.orchestrator.run_command(["pnpm", "--version"])
        actual_pnpm = str(actual_pnpm_res).strip()

        if not actual_pnpm or actual_pnpm != expected_pnpm:
            log_error(f"pnpm version mismatch\nExpected: {expected_pnpm}\nActual:   {actual_pnpm}")
            raise CLIError(f"Run: corepack enable && corepack prepare pnpm@{expected_pnpm} --activate")

        # OpenTelemetry compatibility check for semgrep
        try:
            import importlib.metadata as importlib_metadata
        except ImportError:
            try:
                import importlib_metadata  # type: ignore
            except ImportError:
                importlib_metadata = None  # type: ignore[assignment]

        if importlib_metadata:
            otel_issues = []
            for pkg_name in ["opentelemetry-api", "opentelemetry-sdk"]:
                try:
                    ver = importlib_metadata.version(pkg_name)
                    if ver != "1.37.0":
                        otel_issues.append(f"{pkg_name} ({ver})")
                except Exception as e:
                    log_warn(f"orchestrator: cannot read version for {pkg_name}: {e}")

            if otel_issues:
                print("\n" + "=" * 80)
                print("⚠️  WARNING: OpenTelemetry version conflict detected! ⚠️")
                print(f"Installed versions: {', '.join(otel_issues)}")
                print("Semgrep requires exactly version 1.37.0 of opentelemetry-api and opentelemetry-sdk.")
                print("Using other versions may cause semgrep to crash with ImportError.")
                print("To fix this, please run:")
                print("    pip install opentelemetry-api==1.37.0 opentelemetry-sdk==1.37.0")
                print("=" * 80 + "\n")

        return {"node": actual_node, "pnpm": actual_pnpm}

    def doctor_check(self) -> Dict[str, Any]:
        (
            """Comprehensive """
            """full-stack diagnostic """
            """check covering """
            """Node/pnpm, credentials, """
            """API keys, """
            """and Git """
            """configuration."""
        )
        results: Dict[str, Any] = {
            "node": "unknown",
            "pnpm": "unknown",
            "app_id": "unconfigured",
            "app_private_key": "unconfigured",
            "gemini_api_key": "unconfigured",
            "git_safe_directory": "unconfigured",
            "status": "success",
            "checks": {}
        }

        # 1. Node & pnpm checks
        try:
            rt = self.runtime_check()
            results["node"] = rt.get("node", "unknown")
            results["pnpm"] = rt.get("pnpm", "unknown")
            results["checks"]["runtime"] = {"status": "ok", "node": results["node"], "pnpm": results["pnpm"]}
        except Exception as e:
            results["status"] = "error"
            results["checks"]["runtime"] = {"status": "error", "message": str(e)}

        # 2. GitHub App Credentials
        app_id = os.environ.get("APP_ID") or os.environ.get("GITHUB_APP_ID")
        if app_id and app_id.strip():
            if app_id.strip().isdigit():
                results["app_id"] = "configured"
                results["checks"]["app_id"] = {"status": "ok", "value": app_id.strip()}
            else:
                results["app_id"] = "invalid"
                results["checks"]["app_id"] = {"status": "warning", "message": "APP_ID must be a numeric string"}
        else:
            results["app_id"] = "missing"
            results["checks"]["app_id"] = {"status": "warning", "message": "APP_ID / GITHUB_APP_ID not set"}

        app_key = os.environ.get("APP_PRIVATE_KEY") or os.environ.get("GITHUB_APP_PRIVATE_KEY")
        if app_key and app_key.strip():
            if "BEGIN" in app_key or len(app_key.strip()) > 20:
                results["app_private_key"] = "configured"
                results["checks"]["app_private_key"] = {"status": "ok"}
            else:
                results["app_private_key"] = "invalid"
                results["checks"]["app_private_key"] = {"status": "warning",
                    "message": "APP_PRIVATE_KEY format invalid"}
        else:
            results["app_private_key"] = "missing"
            results["checks"]["app_private_key"] = {"status": "warning",
                "message": "APP_PRIVATE_KEY / GITHUB_APP_PRIVATE_KEY not set"}

        # 3. Gemini API Key
        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_KEY")
        if gemini_key and gemini_key.strip():
            results["gemini_api_key"] = "configured"
            results["checks"]["gemini_api_key"] = {"status": "ok"}
        else:
            results["gemini_api_key"] = "missing"
            results["checks"]["gemini_api_key"] = {"status": "warning", "message": "GEMINI_API_KEY not set"}

        # 4. Git Safe Directory Configuration
        try:
            cwd = os.getcwd()
            safe_dirs_res = dev_tools.orchestrator.run_command(["git", "config", "--get-all", "safe.directory"],
                check=False,
                log_on_error=False)
            safe_dirs_out = safe_dirs_res.stdout if hasattr(safe_dirs_res, "stdout") else str(safe_dirs_res)
            raw_safe_dirs = [d.strip() for d in safe_dirs_out.splitlines() if d.strip()]
            safe_dirs = list(dict.fromkeys(raw_safe_dirs))

            real_cwd = os.path.realpath(cwd)
            is_safe = False
            if "*" in safe_dirs:
                is_safe = True
            else:
                for d in safe_dirs:
                    try:
                        real_d = os.path.realpath(os.path.expanduser(d))
                        if real_cwd == real_d:
                            is_safe = True
                            break
                        rel = os.path.relpath(real_cwd, real_d)
                        if not rel.startswith("..") and not os.path.isabs(rel):
                            is_safe = True
                            break
                    except Exception as e:
                        log_warn(f"orchestrator: path safety probe failed for {d}: {e}")

            is_owner = False
            if hasattr(os, "getuid"):
                try:
                    is_owner = (os.stat(cwd).st_uid == os.getuid())
                except Exception:
                    is_owner = False

            if is_safe or is_owner:
                results["git_safe_directory"] = "configured"
                results["checks"]["git_safe_directory"] = {"status": "ok", "configured_directories": safe_dirs}
            else:
                results["git_safe_directory"] = "unconfigured"
                results["checks"]["git_safe_directory"] = {"status": "warning",
                    "message": "Git dubious ownership or safe.directory missing"}
        except Exception as e:
            results["git_safe_directory"] = "error"
            results["checks"]["git_safe_directory"] = {"status": "warning", "message": str(e)}

        return results

    def generate_ci_summary_report(self) -> str:
        """Generates a markdown summary of CI metrics."""
        metrics_res = verify_ci_metrics()

        report = ["## 📊 CI Metrics Verification"]

        if metrics_res["status"] == "error":
            report.append(f"❌ **FAILED**: {metrics_res['message']}")
        elif metrics_res["status"] == "warning":
            report.append(f"⚠️  **WARNING**: {metrics_res['message']}")
        else:
            report.append("✅ **PASSED**: All metrics within limits.")

        if "metrics" in metrics_res:
            m = metrics_res["metrics"]
            report.append("\n### AI Token Usage")
            report.append(f"- **Input:** {m['inputTokens']} / {m['inputThreshold']}")
            report.append(f"- **Output:** {m['outputTokens']} / {m['outputThreshold']}")
            report.append(f"- **Total:** {m['totalTokens']} / {m['totalThreshold']}")

            report.append("\n<details><summary>Raw Metrics JSON</summary>\n")
            report.append("```json")
            report.append(json.dumps(metrics_res, indent=2))
            report.append("```\n</details>")

        return "\n".join(report)

    def run_preflight(self, limit: int = 10, base_branch: Optional[str] = None) -> Dict[str, Any]:
        """
        Orchestrates td doctor, typechecks, local linting, AST audit, overlap detection, and merge simulation into a unified preflight report.
        """
        results: Dict[str, Any] = {
            "status": "success",
            "doctor": {},
            "typecheck": {},
            "lint": {},
            "audit": {},
            "overlaps": [],
            "merge_simulation": {},
        }

        # 1. Doctor Diagnostics
        try:
            results["doctor"] = self.doctor_check()
        except Exception as e:
            results["doctor"] = {"status": "error", "message": str(e)}

        # 2. Local Typechecks
        if self._pnpm_has_script("type-check"):
            try:
                tsc_res = dev_tools.orchestrator.run_command(["pnpm", "run", "type-check"], check=False)
                results["typecheck"] = {
                    "exit_code": tsc_res.returncode,
                    "status": "success" if tsc_res.returncode == 0 else "error",
                    "output": (tsc_res.stdout or tsc_res.stderr or "")[-2000:],
                }
            except Exception as e:
                results["typecheck"] = {"status": "error", "message": str(e)}
        else:
            results["typecheck"] = {"status": "skipped", "reason": "script not in package.json"}

        # 3. Local Linting Check
        if self._pnpm_has_script("lint"):
            try:
                lint_res = dev_tools.orchestrator.run_command(["pnpm", "run", "lint"], check=False)
                results["lint"] = {
                    "exit_code": lint_res.returncode,
                    "status": "success" if lint_res.returncode == 0 else "error",
                    "output": (lint_res.stdout or lint_res.stderr or "")[-2000:],
                }
            except Exception as e:
                results["lint"] = {"status": "error", "message": str(e)}
        else:
            results["lint"] = {"status": "skipped", "reason": "script not in package.json"}

        # 4. Deterministic AST Audit (repo-aware: only scan targets that exist here)
        try:
            configured_targets = dev_tools.orchestrator.get_config().audit_check_dirs or []
            existing_targets = [t for t in configured_targets if os.path.exists(t)]
            if not existing_targets:
                results["audit"] = {
                    "status": "skipped",
                    "reason": "no configured audit_check_dirs exist in this repo",
                }
            else:
                audit_res = self.get_audit_results(targets=existing_targets)
                results["audit"] = audit_res
                if audit_res.get("violations"):
                    results["audit_status"] = "violations_found"
        except Exception as e:
            results["audit"] = {"error": str(e)}

        # 5. Overlap Detection
        try:
            conflicts = self.detect_conflicts()
            formatted_overlaps = []
            for pr_pair, files in conflicts.items():
                formatted_overlaps.append({"prs": list(pr_pair), "files": files})
            results["overlaps"] = formatted_overlaps
        except Exception as e:
            results["overlaps"] = [{"error": str(e)}]

        # 6. Merge Simulation via git merge-tree (repo-aware base discovery)
        try:
            requested_base = base_branch or dev_tools.orchestrator.get_config().base_branch or "origin/main"
            base_candidates = [requested_base]
            for fallback in ("origin/main", "main", "origin/master", "master"):
                if fallback not in base_candidates:
                    base_candidates.append(fallback)
            merge_base = None
            for cand in base_candidates:
                verify = dev_tools.orchestrator.run_command(
                    ["git", "rev-parse", "--verify", cand], check=False, log_on_error=False
                )
                if verify.returncode == 0:
                    merge_base = cand
                    break
            if merge_base is None:
                results["merge_simulation"] = {
                    "status": "skipped",
                    "reason": f"no base ref found (tried {base_candidates})",
                }
            else:
                curr_branch = dev_tools.orchestrator.run_command(["git", "branch", "--show-current"]).strip() or "HEAD"
                merge_tree_res = dev_tools.orchestrator.run_command(["git", "merge-tree", merge_base, curr_branch],
                    check=False)
                stdout_text = merge_tree_res.stdout or ""
                has_conflicts = "<<<<<<<" in stdout_text
                results["merge_simulation"] = {
                    "base": merge_base,
                    "head": curr_branch,
                    "has_conflicts": has_conflicts,
                    "status": "clean" if not has_conflicts and merge_tree_res.returncode == 0 else ("conflicts_detected" if has_conflicts else "error"),
                }
        except Exception as e:
            results["merge_simulation"] = {"error": str(e)}

        has_errors = (
            results.get("doctor", {}).get("status") == "error"
            or results.get("typecheck", {}).get("status") == "error"
            or results.get("lint", {}).get("status") == "error"
            or results.get("merge_simulation", {}).get("has_conflicts", False)
            or results.get("merge_simulation", {}).get("status") == "error"
        )
        if has_errors:
            results["status"] = "error"

        return results

    def pre_submit_checks(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {"steps": []}

        # 1. Runtime Check (Fail Fast)
        try:
            self.runtime_check()
            results["steps"].append({"name": "Runtime Check", "status": "success"})
        except CLIError as e:
            results["steps"].append({"name": "Runtime Check", "status": "failure", "error": str(e)})
            raise e

        # 2. Automated Validation Steps
        script_path = self._resolve_antipatterns_script()
        steps: List[Tuple[str, List[str]]] = []
        if script_path and os.path.exists(script_path):
            steps.append(("Anti-Pattern Audit", ["node", script_path]))
        steps.append(("Version Downgrade Check",
            [dev_tools.orchestrator.get_config().cli_alias, "gh", "verify-versions"]))
        if self._pnpm_has_script("type-check"):
            steps.append(("TypeScript", ["pnpm", "run", "type-check"]))
        if self._pnpm_has_script("lint"):
            steps.append(("Lint", ["pnpm", "run", "lint"]))

        for name, cmd in steps:
            log_info(f"Running check: {name} ({' '.join(cmd)})")
            try:
                dev_tools.orchestrator.run_command(cmd)
                results["steps"].append({"name": name, "status": "success"})
            except CLIError as e:
                results["steps"].append({"name": name, "status": "failure", "error": str(e)})
                raise e
        missing_vars = [
            v for v in ["BUNDLE_BASELINE_KB", "ANY_COUNT_BASELINE"] if not (os.environ.get(v) or get_gha_variable(v))
        ]
        if missing_vars:
            results["steps"].append(
                {
                    "name": "Baseline Check",
                    "status": "warning",
                    "message": f"Missing GHA variables: {', '.join(missing_vars)}",
                }
            )
        else:
            results["steps"].append({"name": "Baseline Check", "status": "success"})
        scope_warning = verify_pr_scope()
        if scope_warning:
            results["steps"].append({"name": "PR Scope Check", "status": "warning", "message": scope_warning})
        conflicts = self.detect_conflicts()
        results["conflicts"] = [{"prs": list(p), "files": f} for p, f in conflicts.items()]
        return results

    def repair_local(
        self, logs_path: Optional[str] = None, stdin: bool = False, worktree: bool = False
    ) -> Dict[str, Any]:
        logs_content = ""
        if stdin:
            logs_content = sys.stdin.read()
        elif logs_path:
            if os.path.exists(logs_path):
                with open(logs_path, "r", encoding="utf-8") as f:
                    logs_content = f.read()
            else:
                raise CLIError(f"Log file not found: {logs_path}")
        else:
            res_lint = dev_tools.orchestrator.run_command(["pnpm", "run", "lint:ox"], check=False)
            res_tsc = dev_tools.orchestrator.run_command(["pnpm", "run", "type-check"], check=False)
            logs_content = res_lint.stdout + res_lint.stderr + "\n" + res_tsc.stdout + res_tsc.stderr
        if not logs_content.strip():
            return {"status": "success", "message": "No errors found."}
        original_cwd = os.getcwd()
        repair_script = os.path.abspath(os.path.join(original_cwd, "dev-tools", "repair.py"))
        worktree_path = None
        branch_name = None
        try:
            branch_name = f"repair/local-{datetime.now().strftime('%H%M%S')}"
            prefix = dev_tools.orchestrator.get_config().worktree_prefix
            # Create temporary worktree within repo root to avoid Security Error
            worktree_path = os.path.join(original_cwd, f"{prefix}{datetime.now().strftime('%H%M%S')}")
            os.makedirs(worktree_path, exist_ok=True)
            dev_tools.orchestrator.run_command(["git", "worktree", "add", "-b", branch_name, worktree_path, "HEAD"])
            os.chdir(worktree_path)
            if os.path.exists(os.path.join(original_cwd, "node_modules")):
                os.symlink(
                    os.path.join(original_cwd, "node_modules"),
                    os.path.join(worktree_path, "node_modules"),
                )
            # Create temporary log file within repo root logs/
            log_dir = dev_tools.orchestrator.get_or_create_log_dir("repair")
            with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, dir=log_dir) as tmp_log:
                tmp_log.write(logs_content)
                tmp_log_path = tmp_log.name
            cmd = [sys.executable, repair_script, tmp_log_path]
            proc = dev_tools.orchestrator.run_command(cmd, check=False)
            os.unlink(tmp_log_path)
            if proc.returncode == 0:
                return {
                    "status": "success",
                    "message": "Repair completed.",
                    "worktree": worktree_path,
                    "branch": branch_name,
                }
            else:
                return {"status": "error", "message": f"Repair failed with code {proc.returncode}"}
        finally:
            os.chdir(original_cwd)

    def _scan_workflows(self) -> List[str]:
        """Lists all YAML files in .github/workflows/."""
        workflow_dir = ".github/workflows"
        if not os.path.exists(workflow_dir):
            return []
        files = []
        for f in os.listdir(workflow_dir):
            if f.endswith(".yml") or f.endswith(".yaml"):
                files.append(os.path.join(workflow_dir, f))
        return sorted(files)

    def _check_workflow_compliance(self, file_path: str) -> List[str]:
        """Parses a workflow file for compliance violations using a data-driven rule model."""
        violations = []

        stack_versions = dev_tools.orchestrator.get_stack_versions(fetch_latest=False)
        checkout_ver = stack_versions.get("actions/checkout", "v4").lstrip("v")
        setup_node_ver = stack_versions.get("actions/setup-node", "v4").lstrip("v")

        # Rule definition model: dictionaries with regex, message, and optional validator.
        # Regexes are designed to be robust against varying whitespace and formatting.
        rules: List[Dict[str, Any]] = [
            {
                "regex": r"node-version\s*:\s*['\"]?\d+",
                "message": "Hardcoded `node-version:`. Use `node-version-file: '.node-version'` instead.",
            },
            {
                "regex": r"\bnpm\s+(?:install|ci|run)\b",
                "message": "`npm` usage detected. Use `pnpm` exclusively.",
            },
            {
                "regex": r"actions/checkout\s*@\s*v(\d+)",
                "message": f"Outdated `actions/checkout@v{{ver}}`. Use `@v{checkout_ver}`.",
                "validator": lambda m: int(m.group(1)) < int(checkout_ver),
            },
            {
                "regex": r"actions/setup-node\s*@\s*v(\d+)",
                "message": f"Outdated `actions/setup-node@v{{ver}}`. Use `@v{setup_node_ver}`.",
                "validator": lambda m: int(m.group(1)) < int(setup_node_ver),
            },
        ]

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            for rule in rules:
                # Use re.IGNORECASE for robustness against mixed casing in YAML
                regex = rule.get("regex")
                if not isinstance(regex, str):
                    continue
                pattern = re.compile(regex, re.IGNORECASE)
                for match in pattern.finditer(content):
                    validator = rule.get("validator")
                    if validator is None or (callable(validator) and validator(match)):
                        # Support dynamic version reporting if the regex has a group
                        ver = match.group(1) if match.lastindex and match.lastindex >= 1 else ""
                        msg = rule.get("message")
                        if isinstance(msg, str):
                            violations.append(msg.format(ver=ver))

        except Exception as e:
            violations.append(f"Error parsing file: {e}")

        return violations
