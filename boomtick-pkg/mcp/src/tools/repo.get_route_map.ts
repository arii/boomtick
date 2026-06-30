import { z } from "zod";
import { runCommand } from "../lib/shell.js";
import { config } from "../config.js";
import path from "path";

export const GetRouteMapInputSchema = z.object({
  includeStatic: z.boolean().optional(),
});

export async function getRouteMapHandler(args: z.infer<typeof GetRouteMapInputSchema>) {
  GetRouteMapInputSchema.parse(args);
  // Logic based on tech-dancer repo structure: src/config/routes.ts and content/
  const routesPath = path.join(config.repoPath, "src/config/routes.ts");

  // For simplicity in MVP, we'll try to find routes by listing content files
  // and reading the main routes file if it exists.
  let routeMap: Record<string, string> = {};

  try {
    const gitFiles = await runCommand("git", ["ls-files", "content/"]);
    const contentFiles = gitFiles.stdout.trim().split("\n");

    for (const file of contentFiles) {
      if (file.endsWith(".md")) {
        const slug = path.basename(file, ".md");
        if (file.includes("/posts/")) {
          routeMap[`/blog/${slug}`] = file;
        } else if (file.includes("/resources/")) {
          routeMap[`/resources/${slug}`] = file;
        }
      }
    }
  } catch (error) {
    // If no content files, that's fine
  }

  if (args.includeStatic) {
    routeMap["/favicon.ico"] = "public/favicon.ico";
  }
  return { routeMap };
}
