#!/usr/bin/env node
// Vendor the built @arii/boomtick-workflows dist into mcp/dist so the mcp
// package is self-contained after build.
//
// @arii/boomtick-workflows is a private workspace package (not published to
// npm), and the run_workflow gateway imports it at runtime. Any tarball that
// ships that import as a bare specifier is uninstallable: `npm pack` keeps
// "workspace:*" verbatim (npm install -g fails with EUNSUPPORTEDPROTOCOL),
// `pnpm publish` would point at an unpublished registry package, and the CLI
// wheel has no node_modules at all. Copying the built dist into
// dist/vendor/workflows and pointing the emitted dynamic import at a relative
// specifier fixes all of them at once.
//
// This runs after tsc in the mcp build; the source-level package boundary
// stays intact (src keeps importing the workspace package, which resolves via
// the devDependency during type-check and tests).
import { cpSync, existsSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const mcpDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const workflowsDir = path.join(mcpDir, "..", "workflows");
const vendorDir = path.join(mcpDir, "dist", "vendor", "workflows");
const specifier = 'import("@arii/boomtick-workflows")';

const workflowsEntry = path.join(workflowsDir, "dist", "index.js");
if (!existsSync(workflowsEntry)) {
  console.error(
    "vendor-workflows-dist: @arii/boomtick-workflows has no built dist (expected workflows/dist/index.js).\n" +
      "Run `pnpm --filter @arii/boomtick-workflows build` before building @arii/boomtick-mcp.",
  );
  process.exit(1);
}

rmSync(vendorDir, { recursive: true, force: true });
cpSync(path.join(workflowsDir, "dist"), vendorDir, { recursive: true });

// Rewrite the bare dynamic import in every emitted JS file to the vendored
// relative path; only the runtime import remains in dist (type-only imports
// are erased by tsc).
let rewritten = 0;
function walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full);
      continue;
    }
    if (entry.name.endsWith(".js")) {
      const source = readFileSync(full, "utf8");
      if (!source.includes(specifier)) continue;
      const relative = path.relative(path.dirname(full), path.join(vendorDir, "index.js")).split(path.sep).join("/");
      writeFileSync(full, source.replaceAll(specifier, `import("${relative}")`));
      rewritten += 1;
    }
  }
}
walk(path.join(mcpDir, "dist"));

if (rewritten === 0) {
  console.error(
    "vendor-workflows-dist: no emitted file imports @arii/boomtick-workflows; " +
      "the run_workflow gateway import specifier changed — update the rewrite here.",
  );
  process.exit(1);
}
console.log(`Vendored @arii/boomtick-workflows dist (${rewritten} runtime import${rewritten === 1 ? "" : "s"} rewritten).`);
