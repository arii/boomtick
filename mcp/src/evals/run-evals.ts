import { healthHandler } from "../mcp/tools.js";
import { readAgentContextHandler } from "../tools/repo.read_agent_context.js";
import { getPrHandler } from "../tools/github.get_pr.js";

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
      const context = await readAgentContextHandler({});
      const scripts = ("package_scripts" in context ? context.package_scripts : undefined) ?? {};
      console.log(`Found ${Object.keys(scripts).length} scripts.`);
    } catch (e) {
      console.log("Repository scripts fetch failed:", e instanceof Error ? e.message : String(e));
    }

    console.log("\n3. GitHub PR Search (Dry Run):");
    try {
      const prs = await getPrHandler({ state: "open", includeDrafts: true, limit: 100 });
      const prList = (prs as Record<string, unknown>).prs as unknown[];
      console.log(`Found ${prList.length} open PRs.`);
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
