import { z } from "zod";
import { resolveRepo } from "../lib/git.js";
import { runTDCli } from "../lib/tdCli.js";
import { IssueUpdateInputSchema, IssueUpdateResponseSchema } from "./contract.js";

export { IssueUpdateInputSchema };

// The generated schema carries .default(null) on every optional field, so the
// input type (pre-default) — not the parsed output type — is the honest call
// signature; parse applies the defaults.
export async function issueUpdateHandler(args: z.input<typeof IssueUpdateInputSchema>) {
  const params = IssueUpdateInputSchema.parse(args);
  const targetRepo = resolveRepo(params.repo);

  const cmdArgs = ["gh", "issue-update", params.issueNumber.toString()];
  if (params.body) cmdArgs.push("--body", params.body);
  if (params.file) cmdArgs.push("--file", params.file);
  if (params.labels && params.labels.length > 0) cmdArgs.push("--labels", params.labels.join(","));
  if (params.addLabels && params.addLabels.length > 0) cmdArgs.push("--add-labels", params.addLabels.join(","));
  if (params.removeLabels && params.removeLabels.length > 0) cmdArgs.push("--remove-labels", params.removeLabels.join(","));
  if (params.state) cmdArgs.push("--state", params.state);
  cmdArgs.push("--repo", targetRepo);

  const output = IssueUpdateResponseSchema.parse(await runTDCli(cmdArgs, "update issue"));

  return { status: "success", issue: output.issue };
}
