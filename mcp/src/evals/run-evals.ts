import { repoContextHandler } from "../tools/repo.context.js";
import { githubPrHandler } from "../tools/github.pr.js";

async function runEvals() {
  console.log("Starting Boomtick MCP Evaluations...");

  try {
    console.log("\n1. Health Check:");
    try {
      const context = await repoContextHandler({});
      const server = (context as Record<string, unknown>).server;
      console.log(JSON.stringify(server, null, 2));
    } catch (e) {
      console.log("Health check failed:", e instanceof Error ? e.message : String(e));
    }

    console.log("\n2. Repository Scripts:");
    try {
      const context = await repoContextHandler({});
      const scripts = ((context as Record<string, unknown>).packageScripts as Record<string, string>) ?? {};
      console.log(`Found ${Object.keys(scripts).length} scripts.`);
    } catch (e) {
      console.log("Repository scripts fetch failed:", e instanceof Error ? e.message : String(e));
    }

    console.log("\n3. GitHub PR Search (Dry Run):");
    try {
      const prs = await githubPrHandler({ search: { state: "open", limit: 100 } });
      const prList = (prs as Record<string, unknown>).prs as unknown[] | null | undefined;
      console.log(`Found ${(prList ?? []).length} open PRs.`);
    } catch (e) {
      console.log("GitHub search failed (likely due to environment/auth):", e instanceof Error ? e.message : String(e));
    }

    console.log("\nEvaluations complete.");
  } catch (error) {
    console.error("\nEvaluation failed:", error);
    process.exit(1);
  }
}

runEvals();
