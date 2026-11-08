import { z } from "zod";
import { resolveRepo } from "../lib/git.js";
import { runTDCli } from "../lib/tdCli.js";

export const IssueCommentInputSchema = z.object({
  issueNumber: z.number().describe("The number of the issue to comment on."),
  body: z.string().min(1, "Comment body cannot be empty").describe("The content of the comment."),
  repo: z.string().optional().describe("The target repository override (e.g. org/repo)."),
});

const IssueCommentOutputSchema = z.object({
  status: z.string(),
  comment: z.any().optional(),
  message: z.string().optional(),
});

export async function issueCommentHandler(args: z.infer<typeof IssueCommentInputSchema>) {
  const params = IssueCommentInputSchema.parse(args);
  const targetRepo = resolveRepo(params.repo);

  const output = IssueCommentOutputSchema.parse(
    await runTDCli(
      [
        "gh", "issue-comment", params.issueNumber.toString(),
        "--body", params.body,
        "--repo", targetRepo
      ],
      "post comment"
    )
  );

  return { status: "success", comment: output.comment };
}
