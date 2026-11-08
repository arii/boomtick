import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { resolveRepo, getMergeConflictFiles } from "../lib/git.js";
import { sanitizeError } from "../lib/error_utils.js";
import { runTDCli } from "../lib/tdCli.js";
// runCommand("gh", ...) below is a direct gh call for PR metadata, not
// a td call: it intentionally stays on runCommand.

export const GetPrInputSchema = z.object({
  prNumber: z.number().optional().describe("The number of the PR to view. Omit to search open PRs instead."),
  repo: z.string().optional().describe("The target repository override (e.g. org/repo)."),
  includeDiff: z.boolean().optional().describe("Include the PR diff and changed files (absorbs github_get_pr_diff)."),
  includeReviews: z.boolean().optional().describe("Include top-level reviews (absorbs github_get_pr_reviews)."),
  includeCommits: z.boolean().optional().describe("Include commit metadata (absorbs github_get_pr_commits)."),
  includeConflicts: z.boolean().optional().describe("Include merge-conflict files (absorbs github_get_merge_conflict_files)."),
  baseBranch: z.string().optional().describe("Conflict check only: base branch (resolved from PR when omitted)."),
  headRef: z.string().optional().describe("Conflict check only: head ref (resolved from PR when omitted)."),
  state: z.enum(["open", "closed", "all"]).optional().describe("Search mode only: PR state filter (absorbs github_search_open_prs)."),
  includeDrafts: z.boolean().optional().describe("Search mode only: include draft PRs."),
  limit: z.number().min(1).max(100).optional().describe("Search mode only: max PRs to return."),
  labels: z.array(z.string()).optional().describe("Search mode only: filter by labels."),
});

export async function getPrHandler(args: z.infer<typeof GetPrInputSchema>): Promise<Record<string, unknown>> {
  const params = GetPrInputSchema.parse(args);
  const targetRepo = resolveRepo(params.repo);

  if (params.prNumber === undefined) {
    const tdArgs = [
      "gh", "search-prs",
      "--state", params.state ?? "open",
      "--limit", (params.limit ?? 100).toString(),
      "--repo", targetRepo,
    ];
    if (params.includeDrafts === false) {
      tdArgs.push("--no-include-drafts");
    }
    if (params.labels && params.labels.length > 0) {
      tdArgs.push("--labels", params.labels.join(","));
    }
    const output = await runTDCli(tdArgs, "list PRs");
    return { prs: output.prs };
  }

  const output = await runTDCli(
    ["gh", "view", params.prNumber.toString(), "--repo", targetRepo],
    "get PR details"
  );

  const response: Record<string, unknown> = { pr: output.pr };

  if (params.includeDiff) {
    const diff = await runTDCli(
      ["gh", "pr-diff", params.prNumber.toString(), "--repo", targetRepo],
      "get PR diff"
    );
    response.diff = { files: diff.files, diffText: diff.diffText, isTruncated: diff.isTruncated };
  }
  if (params.includeReviews) {
    const reviews = await runTDCli(
      ["gh", "read-pr-reviews", "--pr-number", params.prNumber.toString(), "--repo", targetRepo],
      "read PR reviews"
    );
    response.reviews = reviews.reviews;
    response.reviewCount = reviews.review_count;
  }
  if (params.includeCommits) {
    const commits = await runTDCli(
      ["gh", "list-pr-commits", "--pr-number", params.prNumber.toString(), "--repo", targetRepo],
      "list PR commits"
    );
    response.commits = commits.commits;
  }
  if (params.includeConflicts) {
    let baseBranch = params.baseBranch ?? "main";
    let headRef = params.headRef;
    if (!headRef) {
      const meta = await runCommand("gh", [
        "pr", "view", params.prNumber.toString(),
        "--json", "headRefName,baseRefName", "--repo", targetRepo,
      ]);
      if (meta.exitCode === 0 && meta.stdout.trim()) {
        const info = JSON.parse(meta.stdout);
        if (info.headRefName) headRef = info.headRefName;
        if (info.baseRefName) baseBranch = info.baseRefName;
      }
      headRef ??= "HEAD";
    }
    response.conflictFiles = await getMergeConflictFiles(baseBranch, headRef);
  }

  return response;
}
