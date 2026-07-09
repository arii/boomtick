import re
from typing import List, Optional, Any, Dict, Literal, Union, Annotated
from pydantic import BaseModel, Field, model_validator, ConfigDict, field_validator

class IssueSummary(BaseModel):
    number: int
    title: str
    html_url: str
    state: str

class PRSummary(BaseModel):
    number: int
    title: str
    author: Dict[str, str] = Field(default_factory=dict)
    headRefName: Optional[str] = None
    baseRefName: Optional[str] = None
    isDraft: bool = False
    mergeStateStatus: Optional[str] = None
    updatedAt: Optional[str] = None
    url: Optional[str] = None

class CreateIssueInput(BaseModel):
    title: str = Field(..., min_length=1)
    body: Optional[str] = Field(None, min_length=1)
    file: Optional[str] = Field(None, min_length=1)

    @model_validator(mode='after')
    def check_body_or_file(self) -> 'CreateIssueInput':
        # pylint: disable=no-member
        if (self.body is None or not self.body.strip()) and (self.file is None or not self.file.strip()):
            raise ValueError("Provide either --file or --body (cannot be empty)")
        if self.body and self.file:
            raise ValueError("Provide --file or --body, not both")
        return self

class SearchPRsInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    state: str = Field("open", description="The state of the PRs to search for (open, closed, all).")
    limit: int = Field(100, description="The maximum number of PRs to return (default: 100, range: 1-100).")
    includeDrafts: bool = Field(True, alias="includeDrafts", description="Whether to include draft PRs in the results.")
    labels: Optional[List[str]] = Field(None, description="Filter PRs by labels.")

class IssueUpdateInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    issueNumber: int = Field(..., alias="issueNumber", description="The number of the issue to update.")
    body: Optional[str] = Field(None, description="The new body content for the issue.")
    file: Optional[str] = Field(None, description="Path to file containing new issue body.")
    labels: Optional[List[str]] = Field(None, description="Comma-separated list of labels to set.")
    addLabels: Optional[List[str]] = Field(None, alias="addLabels", description="Comma-separated list of labels to add.")
    removeLabels: Optional[List[str]] = Field(None, alias="removeLabels", description="Comma-separated list of labels to remove.")
    state: Optional[str] = Field(None, description="The state to set the issue to (open or closed).")

    @model_validator(mode='after')
    def check_updates(self) -> 'IssueUpdateInput':
        # pylint: disable=no-member
        if not any([self.body, self.file, self.labels, self.addLabels, self.removeLabels, self.state]):
            raise ValueError("Provide --file, --body, --labels, --addLabels, --removeLabels, or --state")
        if self.body and self.file:
            raise ValueError("Provide --file or --body, not both")
        return self

class CLIResponse(BaseModel):
    status: str = "success"
    message: Optional[str] = None
    data: Optional[Any] = None

class CreateIssueResponse(CLIResponse):
    issue: Optional[IssueSummary] = None

class SearchPRsResponse(CLIResponse):
    prs: List[PRSummary] = Field(default_factory=list)

class IssueUpdateResponse(CLIResponse):
    issue: Optional[IssueSummary] = None

class ReadPRCommentsInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    prNumber: int = Field(..., alias="prNumber", gt=0, description="The PR number to fetch comments for.")

class PRComment(BaseModel):
    user: str
    body: str
    created_at: str

class ReviewComment(BaseModel):
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

class HealthCheckInput(BaseModel):
    checkDeep: bool = Field(False, description="Whether to perform a deep health check including external dependencies.")

class GetPrDiffInput(BaseModel):
    prNumber: int = Field(..., description="The number of the pull request to get the diff for.")

class CheckoutBranchInput(BaseModel):
    branch: str = Field(..., description="The name of the branch to checkout.")
    worktreePath: Optional[str] = Field(None, description="Optional path to the worktree to perform the checkout in.")

class GetMergeConflictFilesInput(BaseModel):
    prNumber: int = Field(..., description="The number of the pull request to check for conflicts.")
    baseBranch: str = Field("main", description="The base branch to check against (default: 'main').")

class GetChangedFilesInput(BaseModel):
    base: str = Field("main", description="The base ref to compare from (default: 'main').")
    head: str = Field("HEAD", description="The head ref to compare to (default: 'HEAD').")

class GetPackageScriptsInput(BaseModel):
    filter: Optional[str] = Field(None, description="Optional glob pattern to filter script names.")

class GetRouteMapInput(BaseModel):
    includeStatic: Optional[bool] = Field(None, description="Whether to include static assets in the route map.")

class ReadCiLogsInput(BaseModel):
    prNumber: int = Field(..., description="The number of the pull request to read logs for.")
    all: bool = Field(False, description="Include logs for successful runs (default: false).")

class RepoLogsInput(BaseModel):
    prNumber: int = Field(..., description="The number of the pull request to stream logs for.")
    grep: Optional[str] = Field(None, description="Optional pattern to filter log lines.")

class CreateBranchInput(BaseModel):
    branchName: str = Field(..., description="The name of the new branch")
    baseBranch: str = Field("main", description="Branch to branch off from")

class CreateRepairBranchInput(BaseModel):
    prNumber: int = Field(..., description="The original pull request number to repair.")
    repairBranchName: Optional[str] = Field(None, description="Optional custom name for the new repair branch.")
    writeMode: bool = Field(..., description="Safety gate: Must be true to perform branch creation and worktree setup.")

class RunTestsInput(BaseModel):
    commands: Optional[List[str]] = Field(None, description="Optional list of commands to run (default includes install, lint, test, build).")
    timeoutSeconds: int = Field(300, description="Maximum time in seconds to wait for tests (default: 300).")
    worktreePath: Optional[str] = Field(None, description="Optional path to the worktree to run tests in.")

class RunLighthouseInput(BaseModel):
    route: str = Field("/", description="The route to audit (default: '/').")
    worktreePath: Optional[str] = Field(None, description="Optional path to the worktree to run the audit in.")

class RunPlaywrightInput(BaseModel):
    grep: Optional[str] = Field(None, description="Optional pattern to filter tests by name.")
    worktreePath: Optional[str] = Field(None, description="Optional path to the worktree to run tests in.")

class CommitPatchInput(BaseModel):
    worktreePath: str = Field(..., description="Path to the worktree where changes are made.")
    message: str = Field(..., description="Commit message.")
    allowedFiles: List[str] = Field(..., description="List of files that are allowed to be committed.")
    writeMode: bool = Field(..., description="Safety gate: Must be true to perform the commit.")

class OpenReplacementPrInput(BaseModel):
    originalPrNumber: int = Field(..., description="The number of the pull request being replaced.")
    repairBranch: str = Field(..., description="The branch containing the fixes.")
    baseBranch: str = Field(..., description="The branch to merge the fixes into.")
    title: str = Field(..., description="The title of the new PR.")
    body: str = Field(..., description="The body/description of the new PR.")
    draft: bool = Field(True, description="Whether to create the PR as a draft (default: true).")
    worktreePath: Optional[str] = Field(None, description="Optional path to the worktree where the PR is created from.")
    pushMode: bool = Field(..., description="Safety gate: Must be true to push the branch and open the PR.")

class CreatePullRequestInput(BaseModel):
    title: str = Field(..., description="PR Title.")
    body: str = Field(..., description="Description of changes.")
    head: str = Field(..., description="The branch containing changes to merge.")
    base: str = Field("main", description="The target branch to merge into.")
    draft: bool = Field(False, description="Whether to create the PR as a draft.")

class CommentTriageSummaryInput(BaseModel):
    prNumber: int = Field(..., description="The number of the original PR to comment on.")
    body: str = Field(..., description="The content of the comment.")

class GetPrInput(BaseModel):
    prNumber: int = Field(..., description="The number of the PR to view.")

class IssueViewInput(BaseModel):
    issueNumber: int = Field(..., description="The number of the issue to view.")

class IssueCommentInput(BaseModel):
    issueNumber: int = Field(..., description="The number of the issue to comment on.")
    body: str = Field(..., description="The content of the comment.")

class CreateJulesSessionInput(BaseModel):
    task: str = Field(..., description="The instructions for Jules.")
    branch: Optional[str] = Field(None, description="The base branch to start from (e.g., 'main').")
    pr: Optional[int] = Field(None, description="The PR number to use as the base branch context.")

class JulesSessionIdInput(BaseModel):
    sessionId: str = Field(..., description="The unique ID of the Jules session.")

class JulesSendMessageInput(BaseModel):
    sessionId: Union[str, List[str]] = Field(..., description="The unique ID or IDs of the Jules session(s).")
    message: str = Field(..., min_length=1, description="The message content to send.")

    @model_validator(mode='after')
    def validate_send_message(self) -> 'JulesSendMessageInput':
        ids = [self.sessionId] if isinstance(self.sessionId, str) else self.sessionId

        # Enforce batch cap of 50
        BATCH_CAP = 50
        if not ids:
            raise ValueError("sessionId list cannot be empty")
        if len(ids) > BATCH_CAP:
            raise ValueError(f"Batch size exceeds maximum limit of {BATCH_CAP}")

        # Allow alphanumeric, hyphens, underscores, and forward slashes (for sessions/ prefix)
        pattern = re.compile(r"^[a-zA-Z0-9/_-]+$")

        for sid in ids:
            if not sid.strip():
                raise ValueError("Session ID cannot be empty or whitespace")
            if not pattern.match(sid):
                raise ValueError(f"Invalid characters in session ID: {sid}")

        if not self.message.strip():
            raise ValueError("Message cannot be empty or whitespace")

        return self

class JulesListSessionsInput(BaseModel):
    pageSize: Optional[int] = Field(None, description="Maximum number of sessions to return.")
    pageToken: Optional[str] = Field(None, description="Token for pagination.")

class SearchDdgsInput(BaseModel):
    query: str = Field(..., description="The search query.")
    maxResults: Optional[int] = Field(None, description="Maximum number of results to return.")

# AI Review Models

class AIReviewIssue(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: Optional[str] = Field(None, description="Unique identifier for the finding.")
    line: Optional[int] = Field(None, description="Line number where the issue occurs.")
    file: Optional[str] = Field(None, description="File path (if not already scoped by AIFileReview).")
    severity: Literal["error", "warn", "info"] = Field(..., description="The severity level.")
    issue: Optional[str] = Field(None, description="Description of the issue (alternative to 'comment').")
    comment: Optional[str] = Field(None, description="Description of the issue.")
    status: Optional[str] = Field("open", description="Status of the finding.")
    confidence: Literal["high", "medium", "low"] = Field(..., description="Confidence level of the AI.")
    counterexample: Optional[str] = Field(None, description="Example of how to fix or why it fails.")
    snippet: Optional[str] = Field(None, description="The exact code snippet from the diff.")

    @field_validator('severity', 'confidence', mode='before')
    @classmethod
    def normalize_enums(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower().strip()
        return v

    @model_validator(mode='before')
    @classmethod
    def reconcile_issue_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Sync issue and comment fields
            issue = data.get('issue')
            comment = data.get('comment')
            if issue and not comment:
                data['comment'] = issue
            elif comment and not issue:
                data['issue'] = comment
        return data

    @model_validator(mode='after')
    def validate_content(self) -> 'AIReviewIssue':
        if not self.issue and not self.comment:
            raise ValueError("AI review issue must have either an 'issue' or 'comment' field.")
        return self

class AIFileReview(BaseModel):
    file: str = Field(..., description="The path of the file being reviewed.")
    issues: List[AIReviewIssue] = Field(default_factory=list, description="List of findings in this file.")
    verdict: str = Field(..., description="The verdict for this file (ok, needs_changes, blocking).")

class AIFullReview(BaseModel):
    file_reviews: List[AIFileReview] = Field(default_factory=list, description="Per-file review results.")
    reviewComment: str = Field(..., description="Overall summary comment for the PR.")
    labels: List[str] = Field(default_factory=list, description="Suggested labels for the PR.")
    recommendation: str = Field(..., description="Final recommendation (Approved, Not Approved, etc).")

class AISynthesisReview(BaseModel):
    reviewComment: str = Field(..., description="Overall summary comment for the PR.")
    labels: List[str] = Field(default_factory=list, description="Suggested labels for the PR.")
    recommendation: str = Field(..., description="Final recommendation.")
