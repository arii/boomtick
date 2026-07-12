# pylint: disable=invalid-name,line-too-long,missing-docstring,no-value-for-parameter
import sys
from collections import defaultdict
from typing import Any, Dict, List

import click
from dev_tools.services.github import GitHubClient
from dev_tools.utils import log_error, log_info


def get_pr_overlaps(github: GitHubClient, limit: int) -> List[Dict[str, Any]]:
    """
    Identifies structural overlaps between open Pull Requests by analyzing modified file sets.

    This function fetches open PRs from the repository, retrieves the list of modified files
    for each PR, and identifies groups (clusters) of PRs that share at least one common file.
    These clusters are useful for identifying potential merge conflicts or functional
    dependencies that might necessitate PR consolidation.

    Args:
        github: An instance of GitHubClient to interact with the GitHub API.
        limit: The maximum number of open PRs to retrieve for analysis.

    Returns:
        A list of cluster dictionaries, each containing:
            - 'prs': A list of PR numbers in the cluster.
            - 'files': A list of filenames shared across the PRs in the cluster.
            - 'metadata': A dictionary mapping PR numbers to their full PR details.
    """
    # 1. Fetch open PRs
    log_info(f"Fetching up to {limit} open PRs...")
    prs = github.list_pull_requests(state="open", limit=limit)

    if not prs:
        log_info("No open PRs found.")
        return []

    # 2. Map files to PRs
    file_to_prs = defaultdict(set)
    pr_metadata = {}

    for pr in prs:
        pr_num = pr["number"]
        pr_metadata[pr_num] = pr
        log_info(f"Fetching files for PR #{pr_num}...")
        try:
            files = github.fetch_pr_files(pr_num)
            for f in files:
                filename = f.get("filename")
                if filename:
                    file_to_prs[filename].add(pr_num)
        except Exception as e:
            log_error(f"Failed to fetch files for PR #{pr_num}: {e}")

    # 3. Identify clusters
    # A cluster is a set of PRs that share at least one file.
    # We use a simple disjoint-set or just group by overlap.
    # For PR consolidation, we want to see pairs/groups that have overlaps.

    overlaps = defaultdict(set)
    for filename, pr_set in file_to_prs.items():
        if len(pr_set) > 1:
            sorted_prs = tuple(sorted(list(pr_set)))
            overlaps[sorted_prs].add(filename)

    clusters = []
    for pr_set, files in overlaps.items():
        clusters.append({
            "prs": list(pr_set),
            "files": sorted(list(files)),
            "metadata": {num: pr_metadata[num] for num in pr_set}
        })

    # Sort clusters by number of overlapping files (descending)
    clusters.sort(key=lambda x: len(x["files"]), reverse=True)
    return clusters


def report_overlaps(clusters: List[Dict[str, Any]]):
    """
    Generates and prints a Markdown-formatted report of identified PR overlaps to stdout.

    The report includes details for each cluster, such as the involved PR numbers,
    the author of each PR, and a list of the primary overlapping files. It also
    provides actionable recommendations for consolidation or coordination.

    Args:
        clusters: A list of cluster dictionaries as returned by `get_pr_overlaps`.
    """
    if not clusters:
        print("✅ No significant PR overlaps detected.")
        return

    print("# Active PR Overlap Analysis")
    print("Identified clusters of PRs with shared file modifications.\n")

    for i, cluster in enumerate(clusters, 1):
        pr_list = cluster["prs"]
        files = cluster["files"]
        metadata = cluster["metadata"]

        print(f"## Cluster {i}: PRs {', '.join(f'#{num}' for num in pr_list)}")
        print(f"**Primary Overlap:** {len(files)} files")

        # List top 10 files
        for f in files[:10]:
            print(f"- `{f}`")
        if len(files) > 10:
            print(f"- ... and {len(files) - 10} more")

        print("\n**Involved PRs:**")
        for num in pr_list:
            pr = metadata[num]
            print(f"- **#{num}**: {pr.get('title')} (Author: @{pr.get('author', {}).get('login', 'unknown')})")

        print("\n**Recommendation:** Merge/Coordinate")
        print("**Rationale:** High file overlap suggests these PRs may have functional dependencies or cause merge conflicts.")
        print("\n---\n")


@click.command()
@click.option("--limit", default=20, help="Limit the number of PRs to process")
@click.option("--no-cache", is_flag=True, help="Bypass the disk cache for GitHub API calls")
def run_cli(limit, no_cache):
    try:
        github = GitHubClient(no_cache=no_cache)
        clusters = get_pr_overlaps(github, limit)
        report_overlaps(clusters)
    except Exception as e:
        log_error(f"Overlap analysis failed: {e}")
        sys.exit(1)


def main():
    run_cli()  # pylint: disable=no-value-for-parameter


if __name__ == "__main__":
    main()
