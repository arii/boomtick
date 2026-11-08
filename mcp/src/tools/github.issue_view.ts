import { z } from "zod";
import { resolveRepo } from "../lib/git.js";
import { runTDCli } from "../lib/tdCli.js";

export const IssueViewInputSchema = z.object({
  issueNumber: z.number().describe("The number of the issue to view."),
  repo: z.string().optional().describe("The target repository override (e.g. org/repo)."),
});

const IssueViewOutputSchema = z.object({
  status: z.string(),
  issue: z.object({
    number: z.number(),
    title: z.string(),
    body: z.string().nullable().optional(),
    state: z.string(),
  }).optional(),
  message: z.string().optional(),
});

export async function issueViewHandler(args: z.infer<typeof IssueViewInputSchema>) {
  const params = IssueViewInputSchema.parse(args);
  const targetRepo = resolveRepo(params.repo);

  const output = IssueViewOutputSchema.parse(
    await runTDCli(
      ["gh", "issue-view", params.issueNumber.toString(), "--repo", targetRepo],
      "view issue"
    )
  );

  return { issue: output.issue };
}
