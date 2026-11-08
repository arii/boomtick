"""GitHub API client (thin aggregator)."""
import requests
import subprocess
from dev_tools.services.gh.reviews import ReviewsMixin
from dev_tools.utils import DiskCache
__all__ = ["DiskCache", "GitHubClient", "requests", "subprocess"]



class GitHubClient(ReviewsMixin):
    """GitHub API client composed of resource mixins."""
