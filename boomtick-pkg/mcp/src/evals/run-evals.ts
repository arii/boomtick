import { healthHandler, HealthCheckInputSchema } from "../mcp/tools.js";
import { searchOpenPrsHandler, SearchOpenPrsInputSchema } from "../tools/github.search_open_prs.js";
import { getPackageScriptsHandler, GetPackageScriptsInputSchema } from "../tools/repo.get_package_scripts.js";

async function runEvals() {
  console.log("Starting Boomtick MCP Evaluations...");

  try {
    console.log("\n1. Health Check:");
    try {
      const health = await healthHandler({ checkDeep: false });
      console.log(JSON.stringify(health, null, 2));
    } catch (e) {
      console.log("Health check failed:", e instanceof Error ? e.message : String(e));
    }

    console.log("\n2. Repository Scripts:");
    try {
      const scripts = await getPackageScriptsHandler({ filter: "" });
      console.log(`Found ${Object.keys(scripts.scripts).length} scripts.`);
    } catch (e) {
      console.log("Repository scripts fetch failed:", e instanceof Error ? e.message : String(e));
    }

    console.log("\n3. GitHub PR Search (Dry Run):");
    try {
      const prs = await searchOpenPrsHandler({ state: "open", includeDrafts: true, limit: 100 });
      console.log(`Found ${prs.prs.length} open PRs.`);
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
