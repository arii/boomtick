import { z } from "zod";
import { resolveRepo } from "../lib/git.js";
import { runTDCli } from "../lib/tdCli.js";

export const IssueCommentInputSchema = z.object({
  issueNumber: z.number().describe("The number of the issue to comment on."),
  body: z.string().min(1, "Comment body cannot be empty").describe("The content of the comment."),
  repo: z.string().optional().describe("The target repository override (e.g. org/repo)."),
});

const IssueCommentSchema = z
  .object({
    id: z.number().optional(),
    html_url: z.string().optional(),
    body: z.string().optional(),
    user: z.object({ login: z.string() }).catchall(z.unknown()).optional(),
    created_at: z.string().optional(),
    updated_at: z.string().optional(),
  })
  .catchall(z.unknown());

export type IssueComment = z.infer<typeof IssueCommentSchema>;

const IssueCommentOutputSchema = z.object({
  status: z.string(),
  comment: IssueCommentSchema.optional(),
  message: z.string().optional(),
});

export async function issueCommentHandler(
  args: z.infer<typeof IssueCommentInputSchema>
): Promise<{ status: "success"; comment: IssueComment | undefined }> {
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
