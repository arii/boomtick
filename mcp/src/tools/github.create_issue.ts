import { z } from "zod";
import { resolveRepo } from "../lib/git.js";
import { runTDCli } from "../lib/tdCli.js";
import { CreateIssueInputSchema, CreateIssueResponseSchema } from "./contract.js";

export { CreateIssueInputSchema };

export async function createIssueHandler(args: z.input<typeof CreateIssueInputSchema>) {
  const params = CreateIssueInputSchema.parse(args);
  const targetRepo = resolveRepo(params.repo);

  const cmdArgs = ["gh", "create-issue", "--title", params.title];
  if (params.body) cmdArgs.push("--body", params.body);
  if (params.file) cmdArgs.push("--file", params.file);
  cmdArgs.push("--repo", targetRepo);

  const output = await runTDCli(cmdArgs, "create issue");

  const parsedOutput = CreateIssueResponseSchema.parse(output);

  return { status: "success", issue: parsedOutput.issue };
}
