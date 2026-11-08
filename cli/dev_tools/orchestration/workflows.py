"""Workflow-graph execution and installer."""
import os
import subprocess
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from dev_tools.utils import CLIError, escape_md, log_warn, sanitize_metadata
from dev_tools.orchestration.planning import PlanningMixin
import dev_tools.orchestrator


if TYPE_CHECKING:
    from dev_tools.workflows.context import WorkflowContext


class WorkflowMixin(PlanningMixin):
    """Workflow-graph execution and installer."""

    def resolve_pr_conflicts(
        self,
        prNumber: int,
        allow_unrelated: bool = False,
        strategy: Optional[str] = None,
        push: bool = False,
        continue_resolve: bool = False,
    ) -> Dict[str, Any]:
        """
        Sets up a worktree for a specific PR and attempts to merge the base branch.
        If continue_resolve is True, it finalizes an in-progress resolution.
        """
        original_cwd = os.getcwd()
        # Use a path that is clearly temporary and matches existing patterns for ignored files
        worktree_path = os.path.join(original_cwd, f"worktree-pr-{prNumber}.tmp")
        changed_dir = False

        try:
            # 1. Fetch PR details early to fail fast
            pr_data = self.github.fetch_pr_details(prNumber)
            default_base = dev_tools.orchestrator.get_config().base_branch_name
            base_branch = pr_data.get("base", {}).get("ref", default_base)
            head_ref = pr_data.get("head", {}).get("ref")

            if not head_ref:
                raise CLIError(f"Could not determine head ref for PR #{prNumber}")

            if continue_resolve:
                if not os.path.exists(worktree_path):
                    raise CLIError(f"No in-progress resolution found for PR #{prNumber} at {worktree_path}")

                changed_dir = True
                os.chdir(worktree_path)

                # Check for unmerged paths
                res_diff = dev_tools.orchestrator.run_command(["git", "diff", "--name-only", "--diff-filter=U"],
                    check=False)
                unmerged = res_diff.stdout.strip()
                if unmerged:
                    raise CLIError(
                        (
                            f"Unresolved "
                            f"conflicts remain "
                            f"in PR "
                            f"#{prNumber}:\n{unmerged}\n\nPlease resolve "
                            f"them in "
                            f"{worktree_path} before "
                            f"continuing."
                        )
                    )

                # Stage all changes
                dev_tools.orchestrator.run_command(["git", "add", "."], check=True)

                # Check if there is anything to commit
                status_res = dev_tools.orchestrator.run_command(["git", "status", "--porcelain"], check=False)
                if status_res.stdout.strip():
                    commit_msg = f"Merge {base_branch} into PR #{prNumber}"
                    dev_tools.orchestrator.run_command(["git", "commit", "-m", commit_msg], check=True)

                # We reuse the push logic below
                res_code = 0
            else:
                # 2. Clean up existing worktree if present
                self._cleanup_worktree(worktree_path)

                # 3. Fetch PR branch and create worktree directly on it
                dev_tools.orchestrator.run_command(["git", "fetch", "origin", f"+pull/{prNumber}/head:{head_ref}"],
                    check=True)
                dev_tools.orchestrator.run_command(["git", "worktree", "add", worktree_path, head_ref], check=True)

                # 4. Switch to worktree and perform git operations
                changed_dir = True
                os.chdir(worktree_path)

                # Ensure origin/base_branch is up-to-date
                dev_tools.orchestrator.run_command(["git", "fetch", "origin", base_branch], check=True)

                # Attempt merge from base branch.
                merge_cmd = [
                    "git",
                    "merge",
                    f"origin/{base_branch}",
                    "-m",
                    f"Merge {base_branch} into PR #{prNumber}",
                ]
                if allow_unrelated:
                    merge_cmd.append("--allow-unrelated-histories")
                if strategy in ["ours", "theirs"]:
                    merge_cmd.extend(["-X", strategy])

                res = dev_tools.orchestrator.run_command(merge_cmd, check=False)
                if not isinstance(res, subprocess.CompletedProcess):
                    raise CLIError("Failed to execute git merge command")

                if res.returncode != 0 and not allow_unrelated:
                    # Detect and retry unrelated histories even if not explicitly requested
                    merge_output = (res.stdout or "") + (res.stderr or "")
                    if "unrelated histories" in merge_output.lower():
                        log_warn(
                            f"Disjoint history detected for PR #{prNumber}. Retrying with --allow-unrelated-histories"
                        )
                        res = dev_tools.orchestrator.run_command(merge_cmd + ["--allow-unrelated-histories"],
                            check=False)
                        if not isinstance(res, subprocess.CompletedProcess):
                            raise CLIError("Retry merge with --allow-unrelated-histories failed execution")

                res_code = res.returncode

            if res_code == 0:
                message = f"✅ PR #{prNumber} merged successfully with {base_branch}."
                if not continue_resolve:
                    message += f"\nPath: {worktree_path}"

                status = "success"

                # Always push if continue_resolve is True, or if push flag was set
                if push or continue_resolve:
                    head_branch = pr_data.get("head", {}).get("ref")
                    if not head_branch:
                        raise CLIError(f"Cannot push: head branch is missing for PR #{prNumber}")
                    try:
                        # Use authenticated URL if token is available to avoid terminal prompts
                        if self.github.token and self.github.repo:
                            auth_url = f"https://x-access-token:{self.github.token}@github.com/{self.github.repo}.git"
                            dev_tools.orchestrator.run_command(["git", "push", auth_url, f"HEAD:{head_branch}"],
                                check=True)
                        else:
                            dev_tools.orchestrator.run_command(["git", "push", "origin", head_branch], check=True)
                        message += f"\n🚀 Successfully pushed resolution to {head_branch}"
                    except Exception as push_err:
                        message += f"\n⚠️  Merge successful but push failed: {str(push_err)}"
                        status = "partial_success"

                if continue_resolve and status == "success":
                    # Cleanup worktree on success
                    os.chdir(original_cwd)
                    changed_dir = False
                    self._cleanup_worktree(worktree_path)
                    message += "\n🧹 Temporary worktree cleaned up."
            else:
                message = (
                    f"⚠️ "
                    f" Conflicts "
                    f"detected in "
                    f"PR #{prNumber} "
                    f"when merging "
                    f"{base_branch}.\nAction Required: "
                    f"Resolve them "
                    f"manually in "
                    f"the worktree.\nCommand: "
                    f"cd {worktree_path}"
                )
                status = "conflict"

            return {
                "status": status,
                "message": message,
                "worktree_path": worktree_path,
                "prNumber": prNumber,
                "base_branch": base_branch,
                "head_branch": head_ref,
            }
        except CLIError:
            raise
        finally:
            if changed_dir:
                os.chdir(original_cwd)

    def generate_aggregation_workflow(self, prNumbers: List[int], target_branch: str) -> Dict[str, Any]:
        """Generates a deterministic aggregation workflow plan for an agent."""
        # 1. Environment Validation
        env_res = self.runtime_check()
        env_output = f"Runtime OK: node {env_res['node']}, pnpm {env_res['pnpm']}"

        # 2. Fetch PR Metadata and Overlaps
        pr_details = {}
        file_to_prs: Dict[str, set[int]] = defaultdict(set)
        pr_hunks = {}

        from dev_tools.utils.concurrency import run_concurrently
        if prNumbers:
            def fetch_pr_info_with_error(pr_num: int):
                try:
                    graphql_data = self.github.fetch_pr_info_graphql(pr_num)
                    details = graphql_data["pr"]
                    files = graphql_data["files"]
                    diff = self.github.fetch_pr_diff(pr_num)
                    hunks = self._extract_diff_hunks(diff)
                    return pr_num, details, files, hunks
                except Exception as e:
                    raise CLIError(f"Failed to fetch info for PR #{pr_num}: {e}")

            results = run_concurrently(fetch_pr_info_with_error, prNumbers, max_workers=4, ignore_exceptions=False)
            for pr_num, details, files, hunks in results:
                pr_details[pr_num] = details
                pr_hunks[pr_num] = hunks
                pr_files = {str(f.get("filename")) for f in files if f.get("filename")}
                for filename_str in pr_files:
                    file_to_prs[filename_str].add(pr_num)

        overlapping_files: Dict[str, List[int]] = {
            f: sorted(list(prs)) for f, prs in file_to_prs.items() if len(prs) > 1
        }

        # 3. Detect Structural Conflicts (Line-level overlaps)
        conflicts: List[Dict[str, Any]] = []
        for filename, prs in overlapping_files.items():
            for i in range(len(prs)):
                for j in range(i + 1, len(prs)):
                    hunks1 = pr_hunks[prs[i]].get(filename, [])
                    hunks2 = pr_hunks[prs[j]].get(filename, [])
                    for s1, e1 in hunks1:
                        for s2, e2 in hunks2:
                            if max(s1, s2) <= min(e1, e2):
                                conflicts.append(
                                    {
                                        "file": filename,
                                        "prs": [prs[i], prs[j]],
                                        "range": [max(s1, s2), min(e1, e2)],
                                    }
                                )

        # 4. Generate Single Consolidated Markdown Plan
        sanitized_target = sanitize_metadata(target_branch)
        workflow_plan_path = os.path.join(
            dev_tools.orchestrator.get_or_create_log_dir("workflows"), f"workflow-plan-aggregation-{sanitized_target}.md"
        )

        plan_lines = []
        plan_lines.append(f"# Aggregation Workflow Plan: {escape_md(target_branch)}\n")
        plan_lines.append("## Agent Instructions")
        plan_lines.append((
            f"- "
            f"**Environment Check**: "
            f"Ensure Python "
            f"dependencies and "
            f"pnpm {dev_tools.orchestrator.get_config().pnpm_version} "
            f"are available."
        ))
        plan_lines.append("- setup complete")
        plan_lines.append("- validation complete")
        plan_lines.append("- context collected")
        plan_lines.append("- overlaps identified")
        plan_lines.append("Agent must not repeat these steps.\n")
        plan_lines.append("---")

        plan_lines.append("\n## Workflow State")
        plan_lines.append("[x] Environment Validation")
        plan_lines.append("[x] PR Context Collection")
        plan_lines.append("[x] Overlap Identification")
        plan_lines.append("[ ] Conflict Resolution")
        plan_lines.append("[ ] Integration Verification")
        plan_lines.append("[ ] Final Aggregation\n")
        plan_lines.append("---")

        plan_lines.append("\n## Targeted PRs & Metadata")
        for pr_num in prNumbers:
            details = pr_details.get(pr_num, {})
            title = escape_md(details.get("title", ""))
            login = escape_md(details.get("user", {}).get("login", "") or details.get("author", {}).get("login", ""))
            head_ref = details.get("head", {}).get("ref", "")
            plan_lines.append(f"- **PR #{pr_num}**: {title} (@{login}) [branch: `{head_ref}`]")

        plan_lines.append("\n## Conflict & Overlap Analysis")
        plan_lines.append("### Overlapping Files")
        if not overlapping_files:
            plan_lines.append("No overlapping files detected.")
        else:
            for filename, prs in sorted(overlapping_files.items()):
                plan_lines.append(f"- `{filename}`: Changed in PRs {', '.join(f'#{p}' for p in prs)}")

        plan_lines.append("\n### Structural Conflicts (Line Overlaps)")
        if not conflicts:
            plan_lines.append("No direct line-level conflicts detected.")
        else:
            for c in conflicts:
                c_file = str(c.get("file", "unknown"))
                c_prs = c.get("prs", [])
                c_range = c.get("range", [0, 0])
                if len(c_prs) >= 2 and len(c_range) >= 2:
                    plan_lines.append(
                        f"- `{c_file}`: PR #{c_prs[0]} and PR #{c_prs[1]} overlap at lines {c_range[0]}-{c_range[1]}"
                    )

        plan_lines.append("\n## Sequential Execution Plan")
        plan_lines.append("### Base Branch Setup")
        plan_lines.append((
            f"1. "
            f"Checkout base "
            f"branch (`{dev_tools.orchestrator.get_config().base_branch_name}`) "
            f"and pull "
            f"latest changes."
        ))
        plan_lines.append((
            f"2. "
            f"Create and "
            f"checkout target "
            f"aggregation branch: "
            f"`git checkout "
            f"-b {escape_md(target_branch)}`."
        ))

        plan_lines.append("\n### Step-by-Step Merge Sequence")
        step_idx = 1
        for pr_num in prNumbers:
            details = pr_details.get(pr_num, {})
            head_ref = details.get("head", {}).get("ref", f"PR #{pr_num}")
            plan_lines.append(f"{step_idx}. **Merge PR #{pr_num}** (`{head_ref}`): `git merge {head_ref}`")
            step_idx += 1

        plan_lines.append("\n### Conflict Resolution & Fallbacks")
        plan_lines.append((
            "- "
            "**Unrelated Histories "
            "Fallback**: If "
            "git fails "
            "with `fatal: "
            "refusing to "
            "merge unrelated "
            "histories`, retry "
            "with `--allow-unrelated-histories`."
        ))
        plan_lines.append((
            "- "
            "**Heavy Conflicts "
            "Fallback**: If "
            "standard merging "
            "creates excessive "
            "noise or "
            "fails, generate "
            "a patch "
            "(`git diff "
            "target...head > "
            "pr_patch.patch`) and "
            "apply manually "
            "(`git apply "
            "pr_patch.patch`)."
        ))

        plan_lines.append("\n## Verification & Completion Checklist")
        plan_lines.append((
            "- "
            "[ ] "
            "**Local Validation**: "
            "Run `pnpm "
            "run lint`, "
            "`pnpm run "
            "type-check`, and "
            "relevant test "
            "suites."
        ))
        plan_lines.append((
            "- "
            "[ ] "
            "**Merge Marker "
            "Check**: Ensure "
            "no remaining "
            "git conflict "
            "markers (`grep "
            "-rn \"^<<<<<<<\" "
            ".`)."
        ))
        plan_lines.append("- [ ] **Final Status Sign-off**: Verify overall stability of the aggregated branch.")

        with open(workflow_plan_path, "w", encoding="utf-8") as f:
            f.write("\n".join(plan_lines) + "\n")

        return {
            "status": "success",
            "plan_path": workflow_plan_path,
            "context_path": workflow_plan_path,
            "skeleton_path": workflow_plan_path,
        }

    def build_context(
        self,
        pr_number: Optional[int] = None,
        issue_number: Optional[int] = None,
        step: str = "generic",
        depth: int = 2,
    ) -> Dict[str, Any]:
        """
        Ingests PR diffs, file trees, and linked issues to dynamically build agent context.
        """
        from dev_tools.services.context_builder import ContextBuilder

        builder = ContextBuilder(github_client=self.github)
        if pr_number is not None:
            builder.ingest_pr(pr_number)
        if issue_number is not None:
            builder.ingest_linked_issue(issue_number)

        builder.ingest_file_tree(max_depth=depth)

        # Optional: Enrich with dependency graph and semantic context if changed files are present
        if pr_number is not None and builder.pr_diff:
            try:
                structured_context = builder.build_structured_context(step)
                changed_files = structured_context.get("pr", {}).get("changed_files", [])
                if changed_files:
                    from dev_tools.services.dependency_graph import DependencyGraph

                    graph = DependencyGraph()
                    affected = graph.find_affected_files(changed_files)
                    if affected:
                        builder.add_extra_context("Affected Files (Impact Analysis)", sorted(list(affected)))
            except Exception as e:
                log_warn(f"Could not calculate affected files for PR context: {e}")

        return {
            "structured": builder.build_structured_context(step),
            "markdown": builder.build_markdown_context(step),
        }

    def run_workflow_graph(
        self,
        graph: Any,
        initial_inputs: Optional[Dict[str, Any]] = None
    ) -> "WorkflowContext":
        """
        Runs a workflow graph using a ContextBuilder-bound WorkflowContext.
        """
        from dev_tools.services.context_builder import ContextBuilder
        from dev_tools.workflows.context import WorkflowContext
        from dev_tools.workflows.runner import WorkflowRunner

        builder = ContextBuilder(github_client=self.github)
        context = WorkflowContext(initial_inputs=initial_inputs, builder=builder)
        runner = WorkflowRunner()

        try:
            return runner.run(graph, context=context)
        finally:
            runner.shutdown(wait=False)

    def install_workflows(self, dry_run: bool = True, cwd: Optional[str] = None) -> Dict[str, Any]:
        """
        Detects if running in a submodule context, and copies/installs standardized automation workflows
        from the submodule directory to the parent repository's .github/workflows/ folder,
        updating composite action path references dynamically.
        """
        if cwd is None:
            cwd = os.path.abspath(os.getcwd())
        else:
            cwd = os.path.abspath(cwd)

        # 1. Detect parent root and submodule directory name
        parent_root = ""
        submodule_name = ""
        submodule_path = cwd

        # Check if current directory is a submodule (running inside the submodule)
        res = subprocess.run(
            ["git", "rev-parse", "--show-superproject-working-tree"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            parent_root = os.path.abspath(res.stdout.strip())
            submodule_name = os.path.basename(cwd)
        else:
            # We might be running inside the parent repository
            # Search for a subdirectory that represents the submodule
            for candidate in ["boomtick-pkg", "boomtick"]:
                candidate_abs = os.path.join(cwd, candidate)
                if os.path.isdir(candidate_abs) and os.path.isdir(os.path.join(candidate_abs, "cli")):
                    parent_root = cwd
                    submodule_name = candidate
                    submodule_path = candidate_abs
                    break

        if not parent_root:
            # Standalone layout fallback
            parent_root = cwd
            submodule_name = ""

        # Workflows to copy
        target_workflows = ["chatops-trigger.yml", "issue-operations.yml", "agent-orchestrator.yml"]
        source_dir = os.path.join(submodule_path, ".github", "workflows")
        target_dir = os.path.join(parent_root, ".github", "workflows")

        copied_files = []
        errors = []

        if not os.path.exists(source_dir):
            raise CLIError(f"Source workflows directory not found: {source_dir}")

        if not dry_run:
            os.makedirs(target_dir, exist_ok=True)

        for filename in target_workflows:
            src_file = os.path.join(source_dir, filename)
            dest_file = os.path.join(target_dir, filename)

            if not os.path.exists(src_file):
                errors.append(f"Source workflow file {filename} not found.")
                continue

            with open(src_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Rewrite paths if we are in submodule layout
            if submodule_name:
                content = content.replace("uses: ./mcp/actions/", f"uses: ./{submodule_name}/mcp/actions/")
                content = content.replace("uses: ./.github/actions/", f"uses: ./{submodule_name}/.github/actions/")
                content = content.replace("$GITHUB_WORKSPACE/cli", f"$GITHUB_WORKSPACE/{submodule_name}/cli")

            if not dry_run:
                with open(dest_file, "w", encoding="utf-8") as f:
                    f.write(content)

            copied_files.append(dest_file)

        return {
            "status": "success" if not errors else "partial_success",
            "parent_root": parent_root,
            "submodule_name": submodule_name,
            "copied_files": copied_files,
            "errors": errors,
            "dry_run": dry_run,
        }
