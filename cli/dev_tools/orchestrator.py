"""Orchestrator (thin aggregator)."""
from dev_tools.services.github import GitHubClient
from dev_tools.config import get_config
from dev_tools.utils import get_or_create_log_dir, get_repo_name, get_stack_versions, run_command
from dev_tools.orchestration.workflows import WorkflowMixin
__all__ = ["GitHubClient",
    "Orchestrator",
    "get_config",
    "get_or_create_log_dir",
    "get_repo_name",
    "get_stack_versions",
    "run_command"]


def __getattr__(name: str):
    if name == "PROJECT_CONFIG":
        return get_config()
    if name == "AUDIT_CHECK_DIRS":
        return get_config().audit_check_dirs
    if name == "SPEC_SECTIONS":
        return get_config().spec_sections
    if name == "UI_INDICATORS":
        return get_config().ui_indicators
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


class Orchestrator(WorkflowMixin):
    """Unified orchestrator composed of concern mixins."""
