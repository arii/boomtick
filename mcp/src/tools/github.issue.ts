import { z } from "zod";
import { resolveRepo } from "../lib/git.js";
import { runTDCli } from "../lib/tdCli.js";
import { GithubIssueInputSchema, GithubIssueResponseSchema } from "./contract.js";

export { GithubIssueInputSchema };

/** The td issue payload shape this handler guarantees, matching the
 * GithubIssueResponse wire schema (camelCase). */
export interface NormalizedIssue {
  number: number;
  title: string;
  body: string | null;
  state: string;
  htmlUrl: string | null;
}

export interface NormalizedComment {
  id: number | null;
  url: string | null;
  body: string | null;
  author: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

// td emits snake_case issue/comment payloads; normalize to the wire shape
// so runtime output always matches the served JSON schema. Unknown input
// shapes degrade to null fields, never to a failed parse on success.
export function normalizeTdIssue(raw: unknown): NormalizedIssue {
  const issue = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const number = Number(issue.number ?? 0);
  return {
    // A malformed number must not surface as NaN in the typed response.
    number: Number.isFinite(number) ? number : 0,
    title: typeof issue.title === "string" ? issue.title : "",
    body: typeof issue.body === "string" ? issue.body : null,
    state: typeof issue.state === "string" ? issue.state : "unknown",
    htmlUrl:
      typeof issue.html_url === "string"
        ? issue.html_url
        : typeof issue.htmlUrl === "string"
          ? issue.htmlUrl
          : null,
  };
}

export function normalizeTdComment(raw: unknown): NormalizedComment {
  const comment = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const user = (comment.user && typeof comment.user === "object" ? comment.user : null) as
    | { login?: unknown }
    | null;
  return {
    id: typeof comment.id === "number" ? comment.id : null,
    url:
      typeof comment.html_url === "string"
        ? comment.html_url
        : typeof comment.url === "string"
          ? comment.url
          : null,
    body: typeof comment.body === "string" ? comment.body : null,
    author: typeof user?.login === "string" ? user.login : null,
    createdAt: typeof comment.created_at === "string" ? comment.created_at : null,
    updatedAt: typeof comment.updated_at === "string" ? comment.updated_at : null,
  };
}

function isWriteField(name: "setBody" | "addLabels" | "removeLabels" | "state", value: unknown): boolean {
  if (value === undefined || value === null) return false;
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

export async function githubIssueHandler(
  args: z.input<typeof GithubIssueInputSchema>
): Promise<Record<string, unknown>> {
  const params = GithubIssueInputSchema.parse(args);
  const targetRepo = resolveRepo(params.repo);

  const wantsComment = params.comment !== undefined;
  const wantsUpdate =
    isWriteField("setBody", params.setBody) ||
    isWriteField("addLabels", params.addLabels) ||
    isWriteField("removeLabels", params.removeLabels) ||
    isWriteField("state", params.state);

  // The wire schema cannot express "exactly one write kind"; enforce here so
  // a comment+update call fails before any td write happens.
  if (wantsComment && wantsUpdate) {
    throw new Error(
      "Exactly one write per call: pass 'comment' or body/label/state changes, not both"
    );
  }

  if (wantsComment) {
    const output = await runTDCli(
      [
        "gh", "issue-comment", params.issueNumber.toString(),
        "--body", params.comment as string,
        "--repo", targetRepo,
      ],
      "post comment"
    );
    return GithubIssueResponseSchema.parse({
      status: "success",
      comment: normalizeTdComment(output.comment),
    });
  }

  if (wantsUpdate) {
    const cmdArgs = ["gh", "issue-update", params.issueNumber.toString()];
    if (params.setBody) cmdArgs.push("--body", params.setBody);
    if (params.addLabels && params.addLabels.length > 0) cmdArgs.push("--add-labels", params.addLabels.join(","));
    if (params.removeLabels && params.removeLabels.length > 0) cmdArgs.push("--remove-labels", params.removeLabels.join(","));
    if (params.state) cmdArgs.push("--state", params.state);
    cmdArgs.push("--repo", targetRepo);

    const output = await runTDCli(cmdArgs, "update issue");
    return GithubIssueResponseSchema.parse({
      status: "success",
      issue: normalizeTdIssue(output.issue),
    });
  }

  // Read mode: no write fields present.
  const output = await runTDCli(
    ["gh", "issue-view", params.issueNumber.toString(), "--repo", targetRepo],
    "view issue"
  );
  return GithubIssueResponseSchema.parse({
    status: "success",
    issue: normalizeTdIssue(output.issue),
  });
}
