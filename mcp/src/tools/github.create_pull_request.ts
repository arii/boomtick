import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { CreatePullRequestInputSchema } from "./contract.js";

export { CreatePullRequestInputSchema };

export async function createPullRequestHandler(args: z.input<typeof CreatePullRequestInputSchema>) {
  const params = CreatePullRequestInputSchema.parse(args);

  const tdArgs = [
    "gh",
    "create-pr",
    "--title", params.title,
    "--body", params.body,
    "--head", params.head,
    "--base", params.base
  ];

  if (params.draft) {
    tdArgs.push("--draft");
  }

  if (params.repo) {
    tdArgs.push("--repo", params.repo);
  }

  const result = await runCommand("td-cli", tdArgs);

  if (result.exitCode !== 0) {
    // Attempt to parse stdout as JSON to see if there's a structured error message
    try {
      const errorOutput = JSON.parse(result.stdout);
      if (errorOutput.status === "error") {
        throw new Error(`Failed to create pull request: ${errorOutput.message}`);
      }
    } catch (e) {
      // If parsing fails, fall back to stderr or a generic message
    }
    throw new Error(`Failed to create pull request: ${result.stderr || result.stdout || "Unknown error"}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`Failed to create pull request: ${output.message}`);
  }

  return {
    success: true,
    url: output.pr.html_url
  };
}
