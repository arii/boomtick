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

// td may print warnings or log lines before/around the JSON payload, so
// parse the {..} span instead of requiring the whole stdout to be JSON.
function extractJsonPayload(text: string): TDCliResponse | null {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start === -1 || end <= start) {
    return null;
  }
  return tryParseJson(text.slice(start, end + 1));
}

// Subcommands that legitimately build indexes and run for minutes; the
// generic shell timeout kills them mid-flight.
const LONG_RUNNING_SUBCOMMANDS = new Set(["init", "audit-code", "audit-impact", "rag"]);
const DEFAULT_TD_TIMEOUT_MS = 60_000;
const LONG_TD_TIMEOUT_MS = 600_000;

export interface TDCliOptions {
  /** Timeout in ms for the underlying td process. Overrides the per-subcommand default. */
  timeoutMs?: number;
}

export async function runTDCli(args: string[], actionName?: string, options: TDCliOptions = {}): Promise<TDCliResponse> {
  const timeoutMs =
    options.timeoutMs ??
    (LONG_RUNNING_SUBCOMMANDS.has(args[0] ?? "") ? LONG_TD_TIMEOUT_MS : DEFAULT_TD_TIMEOUT_MS);
  const result = await runCommand("td", args, { timeout: timeoutMs });
  const stdout = result.stdout.trim();
  const output = extractJsonPayload(stdout);

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
