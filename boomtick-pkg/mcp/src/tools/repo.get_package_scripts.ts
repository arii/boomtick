import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import fs from "fs/promises";
import path from "path";
import { config } from "../config.js";

export const GetPackageScriptsInputSchema = z.object({
  filter: z.string().optional(),
});

export async function getPackageScriptsHandler(args: z.infer<typeof GetPackageScriptsInputSchema>) {
  GetPackageScriptsInputSchema.parse(args);
  const packageJsonPath = path.join(config.repoPath, "package.json");
  try {
    const content = await fs.readFile(packageJsonPath, "utf-8");
    let pkg;
    try {
      pkg = JSON.parse(content);
    } catch (e) {
      throw new Error(`Malformed package.json: ${e instanceof Error ? e.message : String(e)}`);
    }
    let scripts = pkg.scripts || {};
    if (args.filter) {
      const filtered: Record<string, string> = {};
      for (const [name, cmd] of Object.entries(scripts)) {
        if (name.includes(args.filter)) {
          filtered[name] = cmd as string;
        }
      }
      scripts = filtered;
    }
    return { scripts };
  } catch (error) {
    throw new Error(`Failed to read package.json: ${error instanceof Error ? error.message : String(error)}`);
  }
}
