import { runCommand } from "./shell.js";

export interface TDMultiRepoEntry {
  repo?: string;
  path?: string;
  branch?: string;
  commit?: string;
  is_dirty?: boolean;
  has_context?: boolean;
  config?: Record<string, unknown>;
}

export interface TDCliResponse {
  status?: string;
  message?: string;
  code?: number;
  data?: unknown;
  // `td multi-repo status` / `td multi-repo list`
  repos?: TDMultiRepoEntry[];
  total?: number;
  // `td gh search-prs` / `td gh view` / `td gh pr-diff`
  prs?: unknown;
  pr?: unknown;
  files?: unknown;
  diffText?: string;
  isTruncated?: boolean;
  // `td gh read-pr-reviews` / `td gh list-pr-commits`
  reviews?: unknown;
  review_count?: number;
  commits?: unknown;
  // `td repo ci-logs` / `td repo workflow-runs`
  checks?: unknown;
  failedChecks?: unknown;
  logs?: unknown;
  workflow_runs?: unknown;
  // `td gh issue-view` / `td gh issue-comment` / `td gh create-issue` / `td gh issue-update`
  issue?: unknown;
  comment?: unknown;
  // `td agent submit-pr`
  url?: string;
  branch?: string;
  base?: string;
  draft?: boolean;
  [key: string]: unknown;
}

function tryParseJson(text: string): TDCliResponse | null {
  try {
    return JSON.parse(text) as TDCliResponse;
  } catch {
    return null;
  }
}

export async function runTDCli(args: string[], actionName?: string): Promise<TDCliResponse> {
  const result = await runCommand("td", args);
  const stdout = result.stdout.trim();
  const output = stdout.startsWith("{") ? tryParseJson(stdout) : null;

  if (output?.status === "error") {
    const errorMsg = output.message ?? "Unknown error";
    if (actionName) {
      throw new Error(`Failed to ${actionName}: ${errorMsg}`);
    }
    throw new Error(`td returned error: ${errorMsg}`);
  }

  if (result.exitCode !== 0) {
    if (actionName) {
      throw new Error(`Failed to ${actionName}: ${result.stderr || stdout}`);
    }
    throw new Error(`td command failed (${args.join(" ")}): ${result.stderr || stdout}`);
  }

  if (!output) {
    throw new Error(`td returned non-JSON output with exit code 0: ${stdout}`);
  }

  return output;
}
