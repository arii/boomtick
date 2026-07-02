import { runCommand, ShellResult } from "../lib/shell.js";

export async function runTDCli(args: string[]): Promise<any> {
  const result = await runCommand("td-cli", args);

  if (result.exitCode !== 0) {
    throw new Error(`td-cli command failed (${args.join(" ")}): ${result.stderr}`);
  }

  const output = JSON.parse(result.stdout);
  if (output.status === "error") {
    throw new Error(`td-cli returned error: ${output.message}`);
  }

  return output;
}
