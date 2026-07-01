from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Any, Dict

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
        if (self.body is None or not self.body.strip()) and (self.file is None or not self.file.strip()):
            raise ValueError("Provide either --file or --body (cannot be empty)")
        if self.body and self.file:
            raise ValueError("Provide --file or --body, not both")
        return self

class SearchPRsInput(BaseModel):
    state: str = "open"
    limit: int = 100
    include_drafts: bool = True
    labels: Optional[List[str]] = None

class IssueUpdateInput(BaseModel):
    issue_number: int
    body: Optional[str] = None
    file: Optional[str] = None
    labels: Optional[List[str]] = None
    add_labels: Optional[List[str]] = None
    remove_labels: Optional[List[str]] = None
    state: Optional[str] = None

    @model_validator(mode='after')
    def check_updates(self) -> 'IssueUpdateInput':
        if not any([self.body, self.file, self.labels, self.add_labels, self.remove_labels, self.state]):
            raise ValueError("Provide --file, --body, --labels, --add-labels, --remove-labels, or --state")
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
