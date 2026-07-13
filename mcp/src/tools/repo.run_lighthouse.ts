import { z } from "zod";
import { runCommand } from "../lib/shell.js";

export const RunLighthouseInputSchema = z.object({
  route: z.string().optional().default("/"),
  worktreePath: z.string().optional(),
});

export async function runLighthouseHandler(args: z.infer<typeof RunLighthouseInputSchema>) {
  const results = await runCommand("pnpm", ["lhci", "autorun", "--json"], { cwd: args.worktreePath });

  let summary = {};
  const failures: string[] = [];

  try {
    // Attempt to parse summary from LHCI output if available
    // For MVP, we'll provide a structured placeholder if actual JSON isn't present
    if (results.stdout.includes("{")) {
       const possibleJson = results.stdout.substring(results.stdout.indexOf("{"));
       summary = JSON.parse(possibleJson);
    } else {
       summary = {
         performance: 0,
         accessibility: 0,
         bestPractices: 0,
         seo: 0
       };
    }
  } catch (e) {
    failures.push("Failed to parse Lighthouse report");
  }

  return {
    success: results.exitCode === 0,
    route: args.route,
    summary,
    failures,
    command: results.command
  };
}
