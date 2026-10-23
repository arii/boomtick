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

export async function runTDCli(args: string[], actionName?: string): Promise<TDCliResponse> {
  const result = await runCommand("td", args);
  const stdout = result.stdout.trim();
  const output = stdout.startsWith("{") ? tryParseJson(stdout) : null;

  if (output?.status === "error") {
    const errorMsg = output.message ?? "Unknown error";
    if (actionName) {
      throw new Error(`Failed to ${actionName}: ${errorMsg}`);
    }
    throw new Error(`td returned error: ${errorMsg}`);
  }

  if (result.exitCode !== 0) {
    if (actionName) {
      throw new Error(`Failed to ${actionName}: ${result.stderr || stdout}`);
    }
    throw new Error(`td command failed (${args.join(" ")}): ${result.stderr || stdout}`);
  }

  if (!output) {
    throw new Error(`td returned non-JSON output with exit code 0: ${stdout}`);
  }

  return output;
}
