import { runCommand } from "../lib/shell.js";

export interface TDCliResponse {
  status: string;
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

  // Handle structured errors (status: "error") regardless of exit code
  if (output?.status === "error") {
    throw new Error(`td-cli returned error: ${output.message ?? "Unknown error"}`);
  }

  // Handle non-zero exit codes (shell failure)
  if (result.exitCode !== 0) {
    throw new Error(`td-cli command failed (${args.join(" ")}): ${result.stderr || stdout}`);
  }

  // Ensure we have a valid JSON response for successful exit
  if (!output) {
    throw new Error(`td-cli returned non-JSON output with exit code 0: ${stdout}`);
  }

  return output;
}
