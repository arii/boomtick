import { z } from "zod";
import { JulesSession, JulesStatus } from "../types.js";
import { runCommand } from "../../lib/shell.js";

export const CreateJulesSessionInputSchema = z.object({
  task: z.string(),
  branch: z.string().optional(),
  pr: z.number().optional(),
});

export async function createJulesSessionHandler(input: z.infer<typeof CreateJulesSessionInputSchema>): Promise<JulesSession> {
  const apiKey = process.env.JULES_API_KEY;
  if (!apiKey) {
    throw new Error("JULES_API_KEY environment variable is not set.");
  }

  let startingBranch = input.branch || process.env.DEFAULT_BASE_BRANCH || "main";

  if (!input.branch && input.pr) {
    const prResult = await runCommand("gh", [
      "pr",
      "view",
      input.pr.toString(),
      "--json", "headRefName"
    ]);

    if (prResult.exitCode !== 0) {
      throw new Error(`Failed to get PR info for PR #${input.pr}: ${prResult.stderr || "Unknown error (empty stderr)"}`);
    }

    try {
      const prData = JSON.parse(prResult.stdout);
      if (prData.headRefName) {
        startingBranch = prData.headRefName;
      }
    } catch (e) {
      throw new Error(`Failed to parse PR info for PR #${input.pr}: ${e}. Output was: ${prResult.stdout}`);
    }
  }

  const response = await fetch("https://jules.googleapis.com/v1alpha/sessions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": apiKey,
    },
    body: JSON.stringify({
      prompt: input.task,
      sourceContext: {
        source: "sources/github/arii/tech-dancer",
        githubRepoContext: {
          startingBranch: startingBranch,
        },
      },
      automationMode: "AUTO_CREATE_PR",
    }),
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Jules API error (${response.status}): ${errText}`);
  }

  const data = (await response.json()) as any;
  const name = data.name || "";
  const id = name.startsWith("sessions/") ? name.substring(9) : name;

  let status: JulesStatus = "PENDING";
  if (data.state === "SUCCEEDED" || data.state === "COMPLETED") status = "COMPLETED";
  else if (data.state === "FAILED" || data.state === "CANCELLED" || data.state === "TERMINATED") status = "FAILED";
  else if (data.state === "IN_PROGRESS") status = "IN_PROGRESS";

  // Auto-bootstrap: If session is PENDING, send a trigger message to start it
  if (status === "PENDING") {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000); // 15s timeout

      const bootstrapResponse = await fetch(`https://jules.googleapis.com/v1alpha/sessions/${id}:sendMessage`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-goog-api-key": apiKey,
        },
        body: JSON.stringify({
          prompt: input.task,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (bootstrapResponse.ok) {
        status = "IN_PROGRESS";
      } else {
        const errText = await bootstrapResponse.text();
        // eslint-disable-next-line no-console
        // semgrep-ignore: javascript.lang.security.audit.unsafe-formatstring.unsafe-formatstring
        console.error(`Failed to auto-bootstrap session ${id} (HTTP ${bootstrapResponse.status}): ${errText}`);
      }
    } catch (e) {
      // eslint-disable-next-line no-console
        // nosemgrep: javascript.lang.security.audit.unsafe-formatstring.unsafe-formatstring
        console.error(`Failed to auto-bootstrap session ${id}:`, e);
    }
  }

  return {
    id,
    status,
    createdAt: data.createTime ? new Date(data.createTime) : new Date(),
  };
}
