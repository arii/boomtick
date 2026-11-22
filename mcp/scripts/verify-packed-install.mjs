#!/usr/bin/env node
// Prove the packed @arii/boomtick-mcp tarball is self-sufficient (boomtick#1361).
//
// Builds the package, `npm pack`s it, installs the tarball into a clean
// directory outside the workspace (so no repo/workspace node_modules can
// resolve), then imports the vendored workflow registry and runs the
// deterministic echo workflow. A startup handshake alone would not catch a
// missing transitive dependency because the gateway imports lazily.
//
// The run uses an environment with no provider credentials and makes no
// provider requests. Pass --skip-build to reuse an existing mcp/dist.
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const mcpDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const skipBuild = process.argv.includes("--skip-build");
const scratch = mkdtempSync(path.join(os.tmpdir(), "boomtick-mcp-packed-"));

// Strip provider credentials so the proof cannot depend on or reach a provider.
const cleanEnv = Object.fromEntries(
  Object.entries(process.env).filter(([key]) => !/^(OPENROUTER|NEBIUS|OLLAMA|WORKFLOW_LOCAL)_/.test(key)),
);

function run(command, args, options = {}) {
  return execFileSync(command, args, { encoding: "utf8", env: cleanEnv, stdio: ["ignore", "pipe", "inherit"], ...options });
}

function fail(message) {
  console.error(`verify-packed-install: ${message}`);
  process.exitCode = 1;
}

try {
  if (!skipBuild) {
    run("pnpm", ["run", "build"], { cwd: mcpDir, stdio: "inherit" });
  }

  const packOut = run("npm", ["pack", "--json", "--pack-destination", scratch], { cwd: mcpDir });
  const [{ filename }] = JSON.parse(packOut);
  const tarball = path.join(scratch, filename);

  const installDir = path.join(scratch, "install");
  mkdirSync(installDir);
  writeFileSync(path.join(installDir, "package.json"), JSON.stringify({ name: "packed-install-check", private: true, type: "module" }));
  run("npm", ["install", "--ignore-scripts", "--no-audit", "--no-fund", tarball], { cwd: installDir });

  const installedManifest = JSON.parse(
    readFileSync(path.join(installDir, "node_modules", "@arii", "boomtick-mcp", "package.json"), "utf8"),
  );
  const workspaceSpecs = Object.entries({
    ...installedManifest.dependencies,
    ...installedManifest.optionalDependencies,
    ...installedManifest.peerDependencies,
  }).filter(([, spec]) => String(spec).startsWith("workspace:"));
  if (workspaceSpecs.length > 0) {
    throw new Error(`packed manifest contains workspace specifiers: ${JSON.stringify(workspaceSpecs)}`);
  }

  // Run the real handlers (the lazy registry import, then the echo workflow)
  // from the installed package, not from the repo.
  const probe = `
    import { describeWorkflowRegistry, runWorkflowHandler } from "@arii/boomtick-mcp/dist/tools/run_workflow.js";
    const registry = await describeWorkflowRegistry();
    const receipt = await runWorkflowHandler({ workflow: "echo", input: { message: "packed-ok", repeat: 2 } });
    console.log(JSON.stringify({ registry, receipt }));
  `;
  const out = run("node", ["--input-type=module", "-e", probe], { cwd: installDir });
  const { registry, receipt } = JSON.parse(out.trim().split("\n").at(-1));

  const described = JSON.stringify(registry);
  if (!described.includes('"echo"')) throw new Error(`registry does not describe echo: ${described}`);
  if (receipt.status !== "success" || receipt.result?.echoed !== "packed-ok" || receipt.result?.repeat !== 2) {
    throw new Error(`unexpected echo receipt: ${JSON.stringify(receipt)}`);
  }
  console.log("verify-packed-install: ok (vendored registry imported, echo workflow ran from the packed tarball)");
} catch (error) {
  fail(error instanceof Error ? error.message : String(error));
} finally {
  rmSync(scratch, { recursive: true, force: true });
}
