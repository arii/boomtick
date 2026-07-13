import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";

const expectedNodeExact = readFileSync(".node-version", "utf8")
  .trim()
  .replace(/^v/, "");

const actualNode = process.version.replace(/^v/, "");

const pkg = JSON.parse(readFileSync("package.json", "utf8"));

const expectedPnpm = pkg.packageManager?.replace(/^pnpm@/, "");

function getPnpmVersion() {
  try {
    return execSync("pnpm --version", { encoding: "utf8" }).trim();
  } catch {
    return null;
  }
}

const actualPnpm = getPnpmVersion();

let failed = false;

const isCI = process.env.CI === "true" || process.env.CI === "1" || process.env.VERCEL === "1";
const isJules = process.env.USER?.toLowerCase().includes("jules") || process.env.JULES_API_KEY;
const expectedMajorPrefix = expectedNodeExact.split('.')[0] + '.';
const nodeMatches = isCI
  ? (actualNode.startsWith(expectedMajorPrefix) || isJules)
  : actualNode === expectedNodeExact;

const allowNodeChange = process.env.ALLOW_NODE_VERSION_CHANGE === "true";

if (!nodeMatches && !isJules) {
  console.error("❌ Node version mismatch");
  console.error(`Expected: ${expectedNodeExact} (or ${expectedMajorPrefix}x in CI)`);
  console.error(`Actual:   ${actualNode}`);
  console.error("");
  console.error("Hard block: Node.js version modification is forbidden unless ALLOW_NODE_VERSION_CHANGE=true.");
  console.error("Use the repo-pinned version from .node-version / .nvmrc.");
  failed = true;
} else if (actualNode !== expectedNodeExact && !isCI && !isJules && !allowNodeChange) {
  console.error("❌ Node version drift detected");
  console.error(`Local: ${actualNode}, Contract: ${expectedNodeExact}`);
  console.error("Hard block: Node.js version modification is forbidden unless ALLOW_NODE_VERSION_CHANGE=true.");
  failed = true;
}

if (!expectedPnpm) {
  console.error("❌ package.json is missing packageManager");
  console.error('Expected: "packageManager": "pnpm@10.28.2"');
  failed = true;
}

if (!actualPnpm) {
  console.error("❌ pnpm is not available");
  console.error("   It might be disabled or missing from the PATH.");
  console.error(`   Run: corepack enable && corepack prepare pnpm@${expectedPnpm} --activate`);
  failed = true;
} else if (actualPnpm !== expectedPnpm) {
  console.error("❌ pnpm version mismatch");
  console.error(`Expected: ${expectedPnpm}`);
  console.error(`Actual:   ${actualPnpm}`);
  console.error("");
  console.error(`Run: corepack enable && corepack prepare pnpm@${expectedPnpm} --activate`);
  failed = true;
}

if (failed) {
  process.exit(1);
}

console.log(`✅ Runtime OK: node ${actualNode}, pnpm ${actualPnpm}`);
