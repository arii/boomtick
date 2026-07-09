import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const BASELINE_FILE = path.join(ROOT, 'audit-baseline.json');
const SRC_DIR = path.join(ROOT, 'src');

const IGNORE_PATTERN = /impeccable-ignore-file/g;

/**
 * Recursively walks a directory and calls the callback for each file.
 */
function walk(dir, callback) {
  if (!fs.existsSync(dir)) return;
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
      walk(fullPath, callback);
    } else {
      callback(fullPath);
    }
  }
}

/**
 * Scans src directory for 'impeccable-ignore-file' strings.
 */
function getInventory() {
  const inventory = {};
  walk(SRC_DIR, (filepath) => {
    // Audit files based on extensions used in detect-antipatterns.mjs
    if (/\.(tsx?|jsx?|css|scss|yml|md)$/.test(filepath)) {
      try {
        const content = fs.readFileSync(filepath, 'utf8');
        const matches = content.match(IGNORE_PATTERN);
        if (matches) {
          inventory[path.relative(ROOT, filepath)] = matches.length;
        }
      } catch (err) {
        console.warn(`Could not read file ${filepath}: ${err.message}`);
      }
    }
  });
  return inventory;
}

function run() {
  const currentInventory = getInventory();
  const currentCount = Object.values(currentInventory).reduce((a, b) => a + b, 0);

  if (process.argv.includes('--update-baseline')) {
    const baselineData = {
      count: currentCount,
      inventory: currentInventory,
      updatedAt: new Date().toISOString()
    };
    fs.writeFileSync(BASELINE_FILE, JSON.stringify(baselineData, null, 2) + '\n');
    console.log(`\x1b[32m✔ Baseline updated to ${currentCount} suppressions in audit-baseline.json\x1b[0m`);
    process.exit(0);
  }

  console.log('\n\x1b[34m🔍 Scanning for "impeccable-ignore-file" suppressions...\x1b[0m');

  if (Object.keys(currentInventory).length === 0) {
    console.log('No "impeccable-ignore-file" suppressions found.');
  } else {
    console.log('\n\x1b[1mSuppression Inventory:\x1b[0m');
    const sortedFiles = Object.keys(currentInventory).sort();
    for (const file of sortedFiles) {
      console.log(`  \x1b[90m${file}:\x1b[0m \x1b[33m${currentInventory[file]}\x1b[0m`);
    }
  }

  if (!fs.existsSync(BASELINE_FILE)) {
    console.warn('\n\x1b[33m⚠️  No baseline file found at audit-baseline.json.\x1b[0m');
    console.log('Run with --update-baseline to create one.');
    // We don't fail here if no baseline exists, but it's recommended
    process.exit(0);
  }

  const baseline = JSON.parse(fs.readFileSync(BASELINE_FILE, 'utf8'));

  console.log('\n\x1b[1mSummary:\x1b[0m');
  console.log(`  Current suppression count:  \x1b[33m${currentCount}\x1b[0m`);
  console.log(`  Baseline suppression count: \x1b[36m${baseline.count}\x1b[0m`);

  if (currentCount > baseline.count) {
    console.error(`\n\x1b[31m❌ Error: Suppression count (${currentCount}) exceeds baseline (${baseline.count}).\x1b[0m`);
    console.error('Please remove unnecessary "impeccable-ignore-file" markers or update the baseline if justified.');
    console.error('To update baseline: \x1b[1mpnpm run audit:inventory --update-baseline\x1b[0m');
    process.exit(1);
  } else {
    console.log('\n\x1b[32m✅ Suppression count is within baseline.\x1b[0m');
    process.exit(0);
  }
}

run();
