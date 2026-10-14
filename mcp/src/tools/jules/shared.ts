import { JulesSession, JulesStatus } from "../types.js";
import { runCommand } from "../../lib/shell.js";

export interface TDCliResponse {
  status?: string;
  message?: string;
  [key: string]: any;
}

function tryParseJson(text: string): TDCliResponse | null {
  try {
    return JSON.parse(text) as TDCliResponse;
  } catch {
    return null;
  }
}

export async function runTDCli(args: string[]): Promise<TDCliResponse> {
  const result = await runCommand("td-cli", args);
  const stdout = result.stdout.trim();
  const output = stdout.startsWith("{") ? tryParseJson(stdout) : null;

  if (output?.status === "error") {
    throw new Error(`td-cli returned error: ${output.message ?? "Unknown error"}`);
  }

  if (result.exitCode !== 0) {
    throw new Error(`td-cli command failed (${args.join(" ")}): ${result.stderr || stdout}`);
  }

  if (!output) {
    throw new Error(`td-cli returned non-JSON output with exit code 0: ${stdout}`);
  }

  return output;
}

export function parseJulesSession(data: any): JulesSession {
  const name = data.name || "";
  const id = name.startsWith("sessions/") ? name.substring(9) : name;

  let status: JulesStatus = "PENDING";
  if (data.state === "SUCCEEDED" || data.state === "COMPLETED") status = "COMPLETED";
  else if (data.state === "FAILED" || data.state === "CANCELLED" || data.state === "TERMINATED") status = "FAILED";
  else if (data.state === "IN_PROGRESS") status = "IN_PROGRESS";

  let pullRequestUrl: string | undefined;
  if (data.outputs && Array.isArray(data.outputs)) {
    for (const out of data.outputs) {
      if (out.pullRequest && out.pullRequest.url) {
        pullRequestUrl = out.pullRequest.url;
        break;
      }
    }
  }

  return {
    id,
    status,
    createdAt: data.createTime ? new Date(data.createTime) : new Date(),
    pullRequestUrl,
  };
}
