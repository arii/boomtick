import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { resolveRepo } from "../lib/git.js";

export const SearchOpenPrsInputSchema = z.object({
  state: z.enum(["open", "closed", "all"]).optional().default("open"),
  includeDrafts: z.boolean().optional().default(true),
  limit: z.number().min(1).max(100).optional().default(100),
  labels: z.array(z.string()).optional(),
  repo: z.string().optional().describe("The target repository override (e.g. org/repo)."),
});

export async function searchOpenPrsHandler(args: z.infer<typeof SearchOpenPrsInputSchema>) {
  const params = SearchOpenPrsInputSchema.parse(args);
  const targetRepo = resolveRepo(params.repo);

  const tdArgs = [
    "gh", "search-prs",
    "--state", params.state,
    "--limit", params.limit.toString(),
    "--repo", targetRepo,
  ];

  if (!params.includeDrafts) {
    tdArgs.push("--no-include-drafts");
  }

  if (params.labels && params.labels.length > 0) {
    tdArgs.push("--labels", params.labels.join(","));
  }

  const result = await runCommand("td-cli", tdArgs);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to list PRs: ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to list PRs: ${output.message}`);
  }

  return { prs: output.prs };
}
