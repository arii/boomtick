import { z } from "zod";
import { runCommand } from "../../lib/shell.js";
import { config } from "../../config.js";

export const TriggerJulesFeedbackInputSchema = z.object({
  sessionId: z.string(),
});

export async function triggerJulesFeedbackHandler(input: z.infer<typeof TriggerJulesFeedbackInputSchema>) {
  const apiKey = process.env.JULES_API_KEY;
  if (!apiKey) {
    throw new Error("JULES_API_KEY environment variable is not set.");
  }

  const cleanId = input.sessionId.replace("sessions/", "");

  // 1. Get session info to find PR
  const response = await fetch(`https://jules.googleapis.com/v1alpha/sessions/${cleanId}`, {
    method: "GET",
    headers: {
      "x-goog-api-key": apiKey,
    },
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Jules API error (${response.status}): ${errText}`);
  }

  const sessionData = (await response.json()) as any;
  let prNumber: number | undefined;

  // Try to find PR in session outputs
  if (sessionData.outputs && Array.isArray(sessionData.outputs)) {
    for (const output of sessionData.outputs) {
      if (output.pullRequest && output.pullRequest.url) {
        const match = output.pullRequest.url.match(/\/pull\/(\d+)/);
        if (match) {
          prNumber = parseInt(match[1]);
          break;
        }
      }
    }
  }

  // If not found in outputs, search via gh for PRs mentioning the session ID
  if (!prNumber) {
    const prListResult = await runCommand("gh", ["pr", "list", "--state", "open", "--json", "number,title,body"]);
    if (prListResult.exitCode === 0) {
      const prs = JSON.parse(prListResult.stdout);
      for (const pr of prs) {
        if ((pr.title && pr.title.includes(cleanId)) || (pr.body && pr.body.includes(cleanId))) {
          prNumber = pr.number;
          break;
        }
      }
    }
  }

  if (!prNumber) {
    return {
      status: "no_pr_found",
      message: "Could not associate session with an open PR. Ensure the PR is created and contains the session ID in its title or body."
    };
  }

  // 2. Get PR head SHA
  const prViewResult = await runCommand("gh", ["pr", "view", prNumber.toString(), "--json", "headRefOid"]);
  if (prViewResult.exitCode !== 0) {
    throw new Error(`Failed to view PR #${prNumber}: ${prViewResult.stderr}`);
  }
  const sha = JSON.parse(prViewResult.stdout).headRefOid;

  // 3. Get check runs
  const checksResult = await runCommand("gh", ["api", `/repos/${config.githubOwner}/${config.githubRepo}/commits/${sha}/check-runs`]);
  if (checksResult.exitCode !== 0) {
    throw new Error(`Failed to fetch check runs: ${checksResult.stderr}`);
  }
  const checkRuns = JSON.parse(checksResult.stdout).check_runs || [];

  if (checkRuns.length === 0) {
    return { status: "no_checks", message: "No CI checks found for this PR head." };
  }

  const failedChecks = checkRuns.filter((run: any) => run.status === "completed" && run.conclusion === "failure");
  const inProgress = checkRuns.some((run: any) => run.status !== "completed");

  if (inProgress) {
    return { status: "in_progress", message: "CI checks are still in progress. Please try again once they complete." };
  }

  let feedback = "";
  if (failedChecks.length > 0) {
    feedback = "The CI pipeline reported failures. Here are the details:\n\n";
    for (const run of failedChecks) {
      feedback += `### Failed Check: ${run.name}\n`;
      // Fetch logs for failed check
      const jobId = run.external_id;
      if (jobId) {
        const logsResult = await runCommand("gh", ["api", `/repos/${config.githubOwner}/${config.githubRepo}/actions/jobs/${jobId}/logs`]);
        if (logsResult.exitCode === 0) {
          const cleanLogs = cleanGhaLogs(logsResult.stdout);
          const extracted = extractFailingInfo(cleanLogs);
          if (extracted.length > 0) {
            for (const info of extracted) {
              feedback += `- File: \`${info.file}:${info.line}\` (${info.type})\n  Message: ${info.message}\n`;
            }
          } else {
            const lines = cleanLogs.split("\n");
            const snippet = lines.slice(-30).join("\n");
            feedback += `\`\`\`\n${snippet}\n\`\`\`\n`;
          }
        } else {
          feedback += `(Could not retrieve logs: ${logsResult.stderr})\n`;
        }
      } else {
        feedback += `(No Job ID found to retrieve logs)\n`;
      }
      feedback += "\n";
    }
  } else {
    feedback = "All checks passed successfully. You may proceed.";
  }

  // 4. Send message back to Jules
  const sendResponse = await fetch(`https://jules.googleapis.com/v1alpha/sessions/${cleanId}:sendMessage`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": apiKey,
    },
    body: JSON.stringify({
      prompt: feedback,
    }),
  });

  if (!sendResponse.ok) {
    const sendErr = await sendResponse.text();
    throw new Error(`Failed to send feedback to Jules (${sendResponse.status}): ${sendErr}`);
  }

  return { status: "success", feedback };
}

function cleanGhaLogs(logs: string): string {
  return logs
    .replace(/\x1b\[[0-9;]*[mGKF]/g, "") // Strip ANSI
    .split("\n")
    .map(line => line.replace(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s+/, "")) // Strip Timestamps
    .filter(line => line.trim().length > 0)
    .join("\n");
}

function extractFailingInfo(logs: string): any[] {
  const findings: any[] = [];

  // TS Errors
  const tsRegex = /([a-zA-Z0-9_\-\./]+\.[tj]sx?):(\d+):(\d+) - error (TS\d+): (.*)/g;
  let match;
  while ((match = tsRegex.exec(logs)) !== null) {
    findings.push({ file: match[1], line: match[2], message: `${match[4]}: ${match[5]}`, type: "typescript" });
  }

  // Vitest
  const vitestRegex = /FAIL\s+([^\n]+)(?:(?!FAIL).)*?❯\s+([^\n:]+):(\d+):(\d+)/gs;
  while ((match = vitestRegex.exec(logs)) !== null) {
    findings.push({ file: match[2], line: match[3], message: `Test Failure in ${match[1]}`, type: "vitest" });
  }

  // Playwright
  const pwRegex = /\s*\d+\)\s+\[([^\]]+)\]\s+›\s+([^\s:]+):(\d+):(\d+)\s+›\s+(.*)/g;
  while ((match = pwRegex.exec(logs)) !== null) {
    findings.push({ file: match[2], line: match[3], message: `Playwright [${match[1]}] › ${match[5]}`, type: "playwright" });
  }

  return findings;
}
