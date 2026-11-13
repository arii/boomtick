import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { resolveRepo, getMergeConflictFiles } from "../lib/git.js";
import { runTDCli } from "../lib/tdCli.js";
import { GithubPrInputSchema, GithubPrSearchSchema, GithubPrResponseSchema } from "./contract.js";

export { GithubPrInputSchema };

// runCommand("gh", ...) below is a direct gh call for PR metadata, not
// a td call: it intentionally stays on runCommand.

export async function githubPrHandler(
  args: z.input<typeof GithubPrInputSchema>
): Promise<Record<string, unknown>> {
  const params = GithubPrInputSchema.parse(args);
  const targetRepo = resolveRepo(params.repo);
  const include = params.include ?? [];

  // Search mode: explicit search object, never "prNumber omitted means search".
  if (params.search) {
    const search = GithubPrSearchSchema.parse(params.search);
    const tdArgs = [
      "gh", "search-prs",
      "--state", search.state,
      "--limit", search.limit.toString(),
      "--repo", targetRepo,
    ];
    if (search.labels && search.labels.length > 0) {
      tdArgs.push("--labels", search.labels.join(","));
    }
    const output = await runTDCli(tdArgs, "list PRs");
    return GithubPrResponseSchema.parse({ status: "success", prs: output.prs });
  }

  // Workflow-run listing (absorbed repo_get_workflow_runs): the one view
  // mode that does not need a PR number.
  if (include.includes("workflowRuns")) {
    const runs = await runTDCli(["repo", "workflow-runs", "--repo", targetRepo], "fetch workflow runs");
    const response: Record<string, unknown> = { status: "success", workflowRuns: runs.workflow_runs };
    if (params.prNumber !== undefined) {
      return GithubPrResponseSchema.parse({
        ...response,
        ...(await fetchViewSections(params.prNumber, targetRepo, include)),
      });
    }
    return GithubPrResponseSchema.parse(response);
  }

  if (params.prNumber === undefined) {
    throw new Error("Provide prNumber to view a PR, or search to list PRs");
  }

  const output = await runTDCli(
    ["gh", "view", params.prNumber.toString(), "--repo", targetRepo],
    "get PR details"
  );
  return GithubPrResponseSchema.parse({
    status: "success",
    pr: output.pr,
    ...(await fetchViewSections(params.prNumber, targetRepo, include)),
  });
}

async function fetchViewSections(
  prNumber: number,
  targetRepo: string,
  include: string[]
): Promise<Record<string, unknown>> {
  const sections: Record<string, unknown> = {};

  if (include.includes("diff")) {
    const diff = await runTDCli(
      ["gh", "pr-diff", prNumber.toString(), "--repo", targetRepo],
      "get PR diff"
    );
    sections.diff = { files: diff.files, diffText: diff.diffText, isTruncated: diff.isTruncated };
  }
  if (include.includes("reviews")) {
    const reviews = await runTDCli(
      ["gh", "read-pr-reviews", "--pr-number", prNumber.toString(), "--repo", targetRepo],
      "read PR reviews"
    );
    sections.reviews = reviews.reviews;
    sections.reviewCount = reviews.review_count;
  }
  if (include.includes("commits")) {
    const commits = await runTDCli(
      ["gh", "list-pr-commits", "--pr-number", prNumber.toString(), "--repo", targetRepo],
      "list PR commits"
    );
    sections.commits = commits.commits;
  }
  if (include.includes("conflicts")) {
    // Base/head are always resolved from the PR itself: the consolidated
    // surface drops the caller-supplied baseBranch/headRef override params.
    let baseBranch = "main";
    let headRef: string | undefined;
    const meta = await runCommand("gh", [
      "pr", "view", prNumber.toString(),
      "--json", "headRefName,baseRefName", "--repo", targetRepo,
    ]);
    if (meta.exitCode === 0 && meta.stdout.trim()) {
      const info: { headRefName?: unknown; baseRefName?: unknown } = JSON.parse(meta.stdout);
      if (typeof info.headRefName === "string" && info.headRefName) headRef = info.headRefName;
      if (typeof info.baseRefName === "string" && info.baseRefName) baseBranch = info.baseRefName;
    }
    headRef ??= "HEAD";
    sections.conflictFiles = await getMergeConflictFiles(baseBranch, headRef);
  }
  if (include.includes("ciLogs")) {
    sections.ciLogs = await fetchCiLogs(prNumber, targetRepo);
  }
  return sections;
}

/** CI logs for a PR (absorbed repo_read_ci_logs). */
export async function fetchCiLogs(prNumber: number, targetRepo: string): Promise<Record<string, unknown>> {
  const output = await runTDCli(["repo", "ci-logs", prNumber.toString(), "--repo", targetRepo], "fetch CI logs");
  return {
    checks: output.checks,
    failedChecks: output.failedChecks,
    logs: output.logs,
  };
}
