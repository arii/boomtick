import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const GetCommandSchemaInputSchema = z.object({
  commandPath: z.string().describe("The CLI command path to retrieve the schema for (e.g. 'gh audit-pr')"),
});

export async function getCommandSchemaHandler(args: z.infer<typeof GetCommandSchemaInputSchema>) {
  // Sanitize input to prevent command injection (allow only alphanumeric, spaces, hyphens, and underscores)
  const sanitizedPath = args.commandPath.replace(/[^a-zA-Z0-9-_ ]/g, "");
  const result = await runCommand("td-cli", ["schema", sanitizedPath]);

  if (result.exitCode !== 0) {
    // Log stderr for debugging but don't expose it to the user
    // Using comma-separated arguments to satisfy semgrep unsafe-formatstring
    console.error("td-cli schema failed for", sanitizedPath, ":", result.stderr);
    throw new Error(`Failed to get command schema for '${sanitizedPath}'`);
  }

  try {
    const parsed = JSON.parse(result.stdout);
    if (parsed.status === "error") {
      throw new Error(parsed.message || "Failed to get command schema");
    }
    // Return the full payload (which contains the 'schema' object)
    return parsed;
  } catch (e) {
    throw new Error(`Failed to parse command schema output: ${e}`);
  }
}
