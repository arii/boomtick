# pylint: disable=invalid-name,missing-docstring,no-member
import re
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from .base import CamelCaseModel

# Import auto-generated models (fail fast if not generated)
from .contracts import IssueSummary

# Pre-compiled secure regex (whitelists characters and blocks leading/trailing/consecutive slashes)
SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*$")


class PRSummary(CamelCaseModel):
    number: int
    title: str
    author: Dict[str, str] = Field(default_factory=dict)
    head_ref_name: Optional[str] = None
    base_ref_name: Optional[str] = None
    is_draft: bool = False
    merge_state_status: Optional[str] = None
    updated_at: Optional[str] = None
    url: Optional[str] = None


class CreateIssueInput(CamelCaseModel):
    title: str = Field(..., min_length=1)
    body: Optional[str] = Field(None, min_length=1)
    repo: Optional[str] = Field(
        None,
        pattern=r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$",
        description="The target repository override (e.g. org/repo).",
    )


class GithubIssueInput(CamelCaseModel):
    """One tool for issue read + write.

    Omitting every write field reads the issue. A write call performs
    exactly one write kind: `comment` is exclusive with the body/label/
    state update fields (a comment plus a state change in one call would
    make ordering ambiguous in agent receipts).
    """

    issue_number: int = Field(..., description="The number of the issue.")
    repo: Optional[str] = Field(
        None,
        pattern=r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$",
        description="The target repository override (e.g. org/repo).",
    )
    set_body: Optional[str] = Field(
        None, description="Write: the new issue body."
    )
    add_labels: Optional[List[str]] = Field(
        None, description="Write: labels to add."
    )
    remove_labels: Optional[List[str]] = Field(
        None, description="Write: labels to remove."
    )
    state: Optional[Literal["open", "closed"]] = Field(
        None, description="Write: the state to set the issue to."
    )
    comment: Optional[str] = Field(
        None,
        min_length=1,
        description="Write: comment to add (exclusive with the other write fields).",
    )

    @model_validator(mode="after")
    def one_write_per_call(self) -> "GithubIssueInput":
        has_comment = self.comment is not None
        has_update = any(
            v is not None
            for v in (self.set_body, self.add_labels, self.remove_labels, self.state)
        )
        if has_comment and has_update:
            raise ValueError(
                "Exactly one write per call: pass 'comment' or body/label/state changes, not both"
            )
        return self


class CLIResponse(CamelCaseModel):
    status: str = "success"
    message: Optional[str] = None
    data: Optional[Any] = None


class CreateIssueResponse(CLIResponse):
    issue: Optional[IssueSummary] = None


class IssueUpdateResponse(CLIResponse):
    issue: Optional[IssueSummary] = None


class ReadPRCommentsInput(CamelCaseModel):
    pr_number: int = Field(
        ..., gt=0, description="The PR number to fetch comments for."
    )


class PRComment(CamelCaseModel):
    user: str
    body: str
    created_at: str


class ReviewComment(CamelCaseModel):
    user: str
    path: str
    line: Optional[int] = None
    body: str
    created_at: str


class ReadPRCommentsResponse(CLIResponse):
    pr: IssueSummary
    comments: List[PRComment] = Field(default_factory=list)
    review_comments: List[ReviewComment] = Field(default_factory=list)


# MCP Tool Inputs


class RepoContextInput(CamelCaseModel):
    """Read repository context or ecosystem status, with optional server health."""

    repo: Optional[str] = Field(
        None,
        description="Target repository override (e.g. org/repo). Omit for the server's own repo.",
    )
    scope: Optional[Literal["self", "all"]] = Field(
        None,
        description='"all" fetches ecosystem-wide context via td multi-repo status; omit or "self" reads a single repo.',
    )
    skill: Optional[str] = Field(
        None, description="Skill name: include its SKILL.md body in the response."
    )
    deep: Optional[bool] = Field(
        None,
        description="Include server health details (td availability, RAG index state).",
    )

    @model_validator(mode="after")
    def check_scope(self) -> "RepoContextInput":
        if self.scope == "all" and self.repo:
            raise ValueError("Pass scope='all' or repo, not both")
        return self


class RepoTestInput(CamelCaseModel):
    commands: Optional[List[str]] = Field(
        None,
        description="Optional list of commands to run (default includes install, lint, test, build).",
    )
    timeout_seconds: int = Field(
        300, description="Maximum time in seconds to wait for tests (default: 300)."
    )
    worktree_path: Optional[str] = Field(
        None, description="Optional path to the worktree to run tests in."
    )


class RepoTestResponse(CamelCaseModel):
    passed: bool
    exit_code: int
    failed_tests: List[str] = Field(default_factory=list)
    results: List[Dict[str, Any]] = Field(default_factory=list)


class GithubPrSearch(CamelCaseModel):
    state: Literal["open", "closed", "all"] = Field(
        "open", description="PR state filter."
    )
    labels: Optional[List[str]] = Field(None, description="Filter by labels.")
    limit: int = Field(100, ge=1, le=100, description="Maximum PRs to return.")


class GithubPrInput(CamelCaseModel):
    """One tool for PR view (+ optional sections) and PR search.

    Modes are explicit: pass `pr_number` to view one PR, or `search` to
    list PRs — never implicit "prNumber omitted means search".
    """

    pr_number: Optional[int] = Field(
        None, description="PR to view. Required unless 'search' is given."
    )
    repo: Optional[str] = Field(
        None,
        pattern=r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$",
        description="The target repository override (e.g. org/repo).",
    )
    include: List[
        Literal["diff", "reviews", "commits", "conflicts", "ciLogs", "workflowRuns"]
    ] = Field(
        default_factory=list,
        description="View-mode sections to include in the response.",
    )
    search: Optional[GithubPrSearch] = Field(
        None,
        description="Search PRs instead of viewing one. Mutually exclusive with prNumber.",
    )

    @model_validator(mode="after")
    def one_mode(self) -> "GithubPrInput":
        if self.search is not None and self.pr_number is not None:
            raise ValueError("Pass prNumber (view) or search, not both")
        if self.search is None and self.pr_number is None and "workflowRuns" not in self.include:
            raise ValueError(
                "Provide prNumber to view a PR, search to list PRs, "
                "or include=['workflowRuns'] to list recent workflow runs"
            )
        return self


class WorktreeItem(CamelCaseModel):
    worktree_id: str
    path: str
    branch: str
    age_seconds: Union[int, float]
    changed_files_count: int
    disk_usage_bytes: int


class ReadAgentContractInput(CamelCaseModel):
    path: Optional[str] = Field(
        None, description="Local filesystem path to target repository root"
    )
    repo_path: Optional[str] = Field(
        None,
        description="Alias for path (filesystem path to target workspace repository root).",
    )
    repo: Optional[str] = Field(
        None,
        description="Target GitHub repository string (e.g. org/repo).",
    )


class GetContextStatusInput(CamelCaseModel):
    path: Optional[str] = Field(
        None, description="Local filesystem path to target repository root"
    )
    repo_path: Optional[str] = Field(
        None,
        description="Alias for path (filesystem path to target workspace repository root).",
    )
    repo: Optional[str] = Field(
        None,
        description="Target GitHub repository string (e.g. org/repo).",
    )


class TdValidateIssueInput(CamelCaseModel):
    file: str = Field(..., description="Path to the design spec file (or - for stdin).")
    repo_root: Optional[str] = Field(
        None, description="Repo root for file existence checks."
    )


class TdVerifyScopeInput(CamelCaseModel):
    spec_file: str = Field(
        ..., description="Path to the validated design spec markdown file."
    )
    worktree: str = Field(..., description="Path to the worktree to gate.")
    auto_revert: bool = Field(
        False, description="Revert files outside the allowed scope."
    )


class TdAuditWorktreeInput(CamelCaseModel):
    worktree: str = Field(..., description="Path to the worktree to audit.")
    include_impact: bool = Field(
        False, description="Also run blast-radius impact analysis."
    )
    top_k: Optional[int] = Field(None, description="Maximum impacted files to list.")


class TdInitInput(CamelCaseModel):
    repo_root: Optional[str] = Field(
        None, description="Repo root to initialize (default: git root)."
    )


class TdRagInput(CamelCaseModel):
    repo_root: Optional[str] = Field(
        None, description="Repo root for the RAG index (default: git root)."
    )
    query: str = Field(..., description="Natural-language query to run (no rebuild).")
    top_k: Optional[int] = Field(None, description="Maximum RAG hits to return.")


# td CLI responses. The td commands emit flat snake_case JSON via
# out(ctx, msg, data=...) -> {"status": "success", **data} (errors:
# {"status": "error", "message", "code"}), so these models use plain
# BaseModel — field names must match the emitted keys exactly, and the
# camelCase alias generator would describe a wire shape td never emits.
# Every field is optional-with-default so schema validation can never
# fail on a payload td may legally emit; the types describe the success
# payload documented in each td command's docstring.


class TdErrorResponseFields(BaseModel):
    message: Optional[str] = None
    code: Optional[int] = None


class TdInitResponse(TdErrorResponseFields):
    status: Optional[str] = None
    head_sha: Optional[str] = None
    deps_synced: Optional[bool] = None
    deps_note: Optional[str] = None
    main_note: Optional[str] = None
    rag_indexed_sha: Optional[str] = None
    updated_files: List[str] = Field(default_factory=list)


class RagHit(BaseModel):
    content: str = ""
    filepath: str = ""
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    score: Optional[float] = None
    distance: Optional[float] = None


class TdRagResponse(TdErrorResponseFields):
    status: Optional[str] = None
    query: Optional[str] = None
    hits: List[RagHit] = Field(default_factory=list)
    count: int = 0


class TdValidateIssueResponse(TdErrorResponseFields):
    status: Optional[str] = None
    valid: Optional[bool] = None
    allowed_files: List[str] = Field(default_factory=list)
    forbidden_files: List[str] = Field(default_factory=list)
    verification_commands: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class TdVerifyScopeResponse(TdErrorResponseFields):
    status: Optional[str] = None
    passed: Optional[bool] = None
    modified_files: List[str] = Field(default_factory=list)
    violations: List[str] = Field(default_factory=list)
    reverted: List[str] = Field(default_factory=list)


class TdImpactResponse(TdErrorResponseFields):
    status: Optional[str] = None
    passed: Optional[bool] = None
    impacted_files: List[str] = Field(default_factory=list)
    dependent_tests: List[str] = Field(default_factory=list)
    violations: List[Dict[str, Any]] = Field(default_factory=list)
    ui_changed: bool = False
    visual_diff: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TdAuditWorktreeResponse(TdErrorResponseFields):
    status: Optional[str] = None
    passed: Optional[bool] = None
    slop_findings: List[Dict[str, Any]] = Field(default_factory=list)
    suppressions_added: List[str] = Field(default_factory=list)
    ast_violations: List[Dict[str, Any]] = Field(default_factory=list)
    # Present only when the MCP tool ran the blast-radius analysis.
    impact: Optional[TdImpactResponse] = None


# AI Review Models


class AIReviewIssue(CamelCaseModel):
    id: Optional[str] = Field(None, description="Unique identifier for the finding.")
    line: Optional[int] = Field(None, description="Line number where the issue occurs.")
    file: Optional[str] = Field(
        None, description="File path (if not already scoped by AIFileReview)."
    )
    severity: Literal["error", "warn", "info"] = Field(
        ..., description="The severity level."
    )
    issue: Optional[str] = Field(
        None, description="Description of the issue (alternative to 'comment')."
    )
    comment: Optional[str] = Field(None, description="Description of the issue.")
    status: Optional[str] = Field("open", description="Status of the finding.")
    confidence: Literal["high", "medium", "low"] = Field(
        ..., description="Confidence level of the AI."
    )
    counterexample: Optional[str] = Field(
        None, description="Example of how to fix or why it fails."
    )
    snippet: Optional[str] = Field(
        None, description="The exact code snippet from the diff."
    )

    @field_validator("severity", "confidence", mode="before")
    @classmethod
    def normalize_enums(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower().strip()
        return v

    @model_validator(mode="before")
    @classmethod
    def reconcile_issue_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Sync issue and comment fields
            issue = data.get("issue")
            comment = data.get("comment")
            if issue and not comment:
                data["comment"] = issue
            elif comment and not issue:
                data["issue"] = comment
        return data

    @model_validator(mode="after")
    def validate_content(self) -> "AIReviewIssue":
        if not self.issue and not self.comment:
            raise ValueError(
                "AI review issue must have either an 'issue' or 'comment' field."
            )
        return self


class AIFileReview(CamelCaseModel):
    file: str = Field(..., description="The path of the file being reviewed.")
    issues: List[AIReviewIssue] = Field(
        default_factory=list, description="List of findings in this file."
    )
    verdict: str = Field(
        ..., description="The verdict for this file (ok, needs_changes, blocking)."
    )


class AIFullReview(CamelCaseModel):
    file_reviews: List[AIFileReview] = Field(
        default_factory=list, description="Per-file review results."
    )
    review_comment: str = Field(..., description="Overall summary comment for the PR.")
    labels: List[str] = Field(
        default_factory=list, description="Suggested labels for the PR."
    )
    recommendation: str = Field(
        ..., description="Final recommendation (Approved, Not Approved, etc)."
    )


class AISynthesisReview(CamelCaseModel):
    review_comment: str = Field(..., description="Overall summary comment for the PR.")
    labels: List[str] = Field(
        default_factory=list, description="Suggested labels for the PR."
    )
    recommendation: str = Field(..., description="Final recommendation.")


class PrDiffResponse(CamelCaseModel):
    pr_number: int
    files: List[Dict[str, Any]]
    diff_text: str
    is_truncated: bool


class PrCheckSummary(CamelCaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    pending: int = 0
    skipped: int = 0


class PrViewCheck(CamelCaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    conclusion: Optional[str] = None


class PrViewResponse(CamelCaseModel):
    pr_number: int
    title: Optional[str] = None
    state: Optional[str] = None
    draft: bool = False
    review_decision: Optional[str] = None
    mergeable: str = "UNKNOWN"
    checks: List[PrViewCheck] = Field(default_factory=list)
    checks_summary: PrCheckSummary = Field(default_factory=PrCheckSummary)


class RunJobStep(CamelCaseModel):
    number: Optional[int] = None
    name: Optional[str] = None
    status: Optional[str] = None
    conclusion: Optional[str] = None


class RunJob(CamelCaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    status: Optional[str] = None
    conclusion: Optional[str] = None
    html_url: Optional[str] = None
    steps: List[RunJobStep] = Field(default_factory=list)


class RunJobsResponse(CamelCaseModel):
    run_id: int
    total_count: int = 0
    jobs: List[RunJob] = Field(default_factory=list)


# Tool Output Models


class RagHealth(CamelCaseModel):
    index_available: Optional[bool] = None
    last_indexed_at: Optional[str] = None
    doc_count: Optional[int] = None
    index_current: Optional[bool] = None


class ServerHealth(CamelCaseModel):
    github_owner: str = ""
    github_repo: str = ""
    repo_path: str = ""
    read_only: bool = True
    gh_path: str = "gh"
    td_available: Optional[bool] = None
    rag: Optional[RagHealth] = None


class AgentContractSection(CamelCaseModel):
    found: bool = False
    path: str = ""
    content: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class VectorIndexStatus(CamelCaseModel):
    warm: bool = False
    last_warmed_at: Optional[str] = None
    path: str = ""
    stale_files: List[str] = Field(default_factory=list)


class RepoContextResponse(CamelCaseModel):
    """repo_context output: single-repo context, ecosystem status, or both."""

    status: str = "success"
    path: str = ""
    repo: Optional[str] = None
    package_name: str = "boomtick"
    git_commit: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    agent_contract: Optional[AgentContractSection] = None
    package_scripts: Dict[str, str] = Field(default_factory=dict)
    vector_index: Optional[VectorIndexStatus] = None
    skills: List[Dict[str, str]] = Field(default_factory=list)
    skill: Optional[Dict[str, str]] = None
    server: Optional[ServerHealth] = None
    # Ecosystem scope (scope="all") only:
    ecosystem: Optional[bool] = None
    repos: Optional[List[Dict[str, Any]]] = None
    total: Optional[int] = None


class AgentContractConfig(CamelCaseModel):
    base_branch: str = Field("main", description="The default base branch.")
    setup_command: Optional[str] = Field(
        None, description="Command to set up dependencies."
    )
    test_command: Optional[str] = Field(None, description="Command to run tests.")
    lint_command: Optional[str] = Field(None, description="Command to run linter.")
    build_command: Optional[str] = Field(
        None, description="Command to build the project."
    )
    shared_deps: Literal["symlink", "install", "none"] = Field(
        "symlink", description="Dependency sharing strategy."
    )
    sparse_paths: Optional[List[str]] = Field(
        None, description="Optional sparse checkout paths."
    )
    worktree_ttl_days: int = Field(7, description="Worktree TTL in days.")


class ReadAgentContractResponse(CamelCaseModel):
    status: str = "success"
    content: Optional[str] = Field(
        None, description="The content of the agent contract specification file."
    )
    path: Optional[str] = Field(None, description="Path to the agent contract file.")
    config: Optional[AgentContractConfig] = Field(
        None,
        description="Parsed agent contract configuration.",
    )


class GetContextStatusResponse(CamelCaseModel):
    warm: bool = Field(
        ..., description="Whether the .agent-context.json index is warm and up-to-date."
    )
    last_warmed_at: Optional[str] = Field(
        None,
        description="ISO timestamp when .agent-context.json was last updated or created.",
    )
    path: str = Field(..., description="Path to .agent-context.json.")
    stale_files: List[str] = Field(
        default_factory=list,
        description="List of files that are newer than .agent-context.json or stale.",
    )


class CheckoutBranchResponse(CamelCaseModel):
    success: bool = True
    branch: str


class GithubCiLogsPayload(CamelCaseModel):
    checks: Optional[List[Dict[str, Any]]] = None
    failed_checks: Optional[List[Dict[str, Any]]] = None
    logs: Optional[Union[Dict[str, Any], List[Any], str]] = None
    workflow_runs: Optional[List[Dict[str, Any]]] = None


class CreateBranchResponse(CamelCaseModel):
    success: bool = True
    branch_name: str
    base_branch: Optional[str] = None
    repo: Optional[str] = None
    path: Optional[str] = None


class CreateRepairBranchResponse(CamelCaseModel):
    pr_number: int
    original_branch: str
    repair_branch: str
    base_branch: str
    worktree_path: str
    repo: Optional[str] = None
    path: Optional[str] = None
    base_sha: Optional[str] = None
    pr_head_sha: Optional[str] = None
    fetched: bool = False


class OpenReplacementPrResponse(CamelCaseModel):
    success: bool = True
    url: str


class CreatePullRequestResponse(CamelCaseModel):
    success: bool = True
    url: str


class CommentTriageSummaryResponse(CamelCaseModel):
    success: bool = True
    comment_url: str


class GithubIssueDetail(CamelCaseModel):
    number: int
    title: str
    body: Optional[str] = None
    state: str
    html_url: Optional[str] = None


class GithubIssueCommentPayload(CamelCaseModel):
    id: Optional[int] = None
    url: Optional[str] = None
    body: Optional[str] = None
    author: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class GithubIssueResponse(CamelCaseModel):
    status: str = "success"
    # Read mode: the issue as td reports it (normalized).
    issue: Optional[GithubIssueDetail] = None
    # Comment mode: the comment as td reports it (normalized).
    comment: Optional[GithubIssueCommentPayload] = None


class GithubPrDiffPayload(CamelCaseModel):
    files: List[Dict[str, Any]] = Field(default_factory=list)
    diff_text: str = ""
    is_truncated: bool = False


class GithubPrResponse(CamelCaseModel):
    status: str = "success"
    # View mode.
    pr: Optional[Dict[str, Any]] = None
    # Search mode.
    prs: Optional[List[Dict[str, Any]]] = None
    diff: Optional[GithubPrDiffPayload] = None
    reviews: Optional[List[Dict[str, Any]]] = None
    review_count: Optional[int] = None
    commits: Optional[List[Dict[str, Any]]] = None
    conflict_files: Optional[List[str]] = None
    ci_logs: Optional[GithubCiLogsPayload] = None
    # Workflow-run listing mode (include=["workflowRuns"], no PR number
    # required) — absorbed repo_get_workflow_runs.
    workflow_runs: Optional[List[Dict[str, Any]]] = None


class AgentStatusInput(CamelCaseModel):
    session_id: str = Field(
        ..., description="The ID of the session to check status for"
    )


class AgentStatusVerification(CamelCaseModel):
    tests_passed: bool
    errors: Optional[str] = None
    exit_code: Optional[int] = None


class AgentStatusResponse(CamelCaseModel):
    session_id: str
    worktree_id: str
    state: Literal["running", "done", "failed"]
    last_checkpoint: str
    changed_files: List[str] = Field(default_factory=list)
    last_verification: Optional[AgentStatusVerification] = None


class SkillInfo(CamelCaseModel):
    name: str
    description: str


class AgentSubmitPrInput(CamelCaseModel):
    repo: Optional[str] = Field(
        None, description="Target repository override (e.g. owner/repo)"
    )
    branch: str = Field(..., description="Branch to push and submit as a PR")
    base_branch: str = Field("main", description="Base branch for the PR")
    title: str = Field(..., description="PR title")
    body: str = Field("", description="PR body")
    draft: bool = Field(True, description="Open the PR as a draft for human review")
    worktree_path: Optional[str] = Field(None, description="Worktree to push from")
    push_mode: bool = Field(
        False, description="Safety gate: must be true to push and open the PR"
    )


class AgentSubmitPrResponse(CamelCaseModel):
    status: str = "success"
    url: Optional[str] = None
    branch: str = ""
    base_branch: str = "main"
    draft: bool = True


class SuggestCounts(CamelCaseModel):
    open_prs: int = 0
    failing_runs: int = 0
    active_sessions: int = 0


class SuggestNextActionResponse(CamelCaseModel):
    status: str = "success"
    suggestion: str
    fast_path: bool
    counts: SuggestCounts
    runnable_command: Optional[str] = None
