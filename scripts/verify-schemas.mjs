import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

/**
 * Orchestrates the validation pipeline:
 * Python models -> CLI schema -> TS contracts -> MCP schemas
 */
async function verifySchemas() {
  console.log('🔍 Starting schema validation pipeline...');

  // 1. Identify Python interpreter
  const pythonPath = existsSync('.venv/bin/python3') ? '.venv/bin/python3' : 'python3';
  console.log(`🐍 Using Python: ${pythonPath}`);

  // 2. Generate CLI schema from Python models
  try {
    console.log('🔄 Step 1/3: Generating CLI schema from Python models...');
    execSync(`export PYTHONPATH="$PYTHONPATH:${join(process.cwd(), 'cli')}" && ${pythonPath} cli/dev_tools/schema_gen.py`, {
      stdio: 'inherit',
      env: { ...process.env }
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

verifySchemas().catch((_error) => {
  console.error('❌ Unexpected error in schema validation pipeline:', error);
  process.exit(254);
});
