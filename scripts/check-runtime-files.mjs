import { existsSync, readFileSync } from "node:fs";

const expectedNodeExact = "24.16.0";
const expectedNodeMajorForVercel = "24.x";
const expectedPnpm = "10.28.2";

const errors = [];

function readTrimmed(path) {
  return readFileSync(path, "utf8").trim().replace(/^v/, "");
}

const nvmrc = readTrimmed(".nvmrc");
const nodeVersionFile = readTrimmed(".node-version");
const pkgPath = existsSync("package.json") ? "package.json" : "mcp/package.json";
const pkg = JSON.parse(readFileSync(pkgPath, "utf8"));

if (nvmrc !== expectedNodeExact) {
  errors.push(`.nvmrc must be ${expectedNodeExact}, found ${nvmrc}`);
}

if (nodeVersionFile !== expectedNodeExact) {
  errors.push(`.node-version must be ${expectedNodeExact}, found ${nodeVersionFile}`);
}

if (pkg.packageManager !== `pnpm@${expectedPnpm}`) {
  errors.push(`packageManager must be pnpm@${expectedPnpm}, found ${pkg.packageManager}`);
}

if (pkg.engines?.node !== expectedNodeMajorForVercel) {
  errors.push(`engines.node must be ${expectedNodeMajorForVercel}, found ${pkg.engines?.node}`);
}

if (pkg.engines?.pnpm !== expectedPnpm) {
  errors.push(`engines.pnpm must be ${expectedPnpm}, found ${pkg.engines?.pnpm}`);
}

const allowNodeChange = process.env.ALLOW_NODE_VERSION_CHANGE === "true";
if (!allowNodeChange) {
    if (nvmrc !== expectedNodeExact || nodeVersionFile !== expectedNodeExact || pkg.engines?.node !== expectedNodeMajorForVercel) {
        // This is a bit redundant with the individual checks above but ensures a clear "Hard block" message
        errors.push("HARD BLOCK: Node.js version modification is forbidden unless ALLOW_NODE_VERSION_CHANGE=true.");
    }
}

if (errors.length > 0) {
  console.error("❌ Runtime contract drift detected:");
  for (const error of errors) {
    console.error(`- ${error}`);
  }
  console.error("");
  console.error("Do not change runtime files unless the task explicitly updates the runtime contract.");
  process.exit(1);
}

console.log("✅ Runtime contract files are consistent");
