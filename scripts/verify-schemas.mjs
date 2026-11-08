import { execSync, execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, delimiter } from 'node:path';

/**
 * Orchestrates the validation pipeline:
 * Python models -> CLI schema -> TS contracts -> MCP schemas
 */
async function verifySchemas() {
  console.log('🔍 Starting schema validation pipeline...');

  // 1. Identify Python interpreter (pinned venv path only; fail closed when absent).
  const pythonPath = '.venv/bin/python3';
  if (!existsSync(pythonPath)) {
    console.error(`❌ Missing required toolchain binary: ${pythonPath}. Run ./setup-agent.sh to provision the venv, then retry.`);
    process.exit(254);
  }
  console.log(`🐍 Using Python: ${pythonPath}`);

  // 2. Generate CLI schema from Python models
  try {
    console.log('🔄 Step 1/3: Generating CLI schema from Python models...');
    const cliDir = join(process.cwd(), 'cli');
    const existingPythonPath = process.env.PYTHONPATH || '';
    const newPythonPath = existingPythonPath
      ? `${existingPythonPath}${delimiter}${cliDir}`
      : cliDir;

    const tdPath = '.venv/bin/td';
    if (!existsSync(tdPath)) {
      console.error(`❌ Missing required toolchain binary: ${tdPath}. Run ./setup-agent.sh to provision the venv, then retry.`);
      process.exit(254);
    }
    execFileSync(tdPath, ['schema', '--generate'], {
      stdio: 'inherit',
      env: {
        ...process.env,
        PYTHONPATH: newPythonPath,
      },
    });
  } catch (_error) {
    console.error('❌ Failed to generate CLI schema.');
    process.exit(254);
  }

  // 3. Sync TS contracts from CLI schema
  try {
    console.log('🔄 Step 2/3: Synchronizing TS contracts...');
    execSync('pnpm --filter @arii/boomtick-mcp sync-contracts', {
      stdio: 'inherit'
    });
  } catch (_error) {
    console.error('❌ Failed to synchronize TS contracts.');
    process.exit(254);
  }

  // 4. Sync MCP schemas
  try {
    console.log('🔄 Step 3/3: Synchronizing MCP schemas...');
    execSync('pnpm --filter @arii/boomtick-mcp sync:mcp-schemas', {
      stdio: 'inherit'
    });
  } catch (_error) {
    console.error('❌ Failed to synchronize MCP schemas.');
    process.exit(254);
  }

  console.log('✅ Schema validation pipeline completed successfully.');
}

verifySchemas().catch((error) => {
  console.error('❌ Unexpected error in schema validation pipeline:', error);
  process.exit(254);
});
