import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

/**
 * Orchestrates the schema verification and synchronization process.
 */
function verifySchemas() {
  if (process.env.SKIP_BOOMTICK_PKG === 'true' || process.env.VERCEL === '1') {
    console.log('⏭️ Skipping schema verification (SKIP_BOOMTICK_PKG is true or on Vercel).');
    return;
  }

  const root = process.cwd();

  // 1. Check dependencies
  console.log('🔍 Checking dependencies...');
  const rootNodeModules = join(root, 'node_modules');
  const mcpNodeModules = join(root, 'mcp', 'node_modules');

  if (!existsSync(rootNodeModules) && !existsSync(mcpNodeModules)) {
    console.error('❌ Error: node_modules is missing.');
    console.error('   Please run `pnpm install` in the root directory to set up dependencies.');
    process.exit(1);
  }

  try {
    // Determine python command (use .venv if it exists)
    const venvPython = join(root, '.venv', 'bin', 'python3');
    const pythonCmd = existsSync(venvPython) ? venvPython : 'python3';

    // 2. Python Dependency Check
    console.log(`🐍 Checking Python dependencies using ${pythonCmd}...`);
    try {
      execSync(`${pythonCmd} -c "import pydantic"`, { stdio: 'pipe' });
    } catch {
      console.error('❌ Error: Python dependency `pydantic` is missing.');
      console.error('   Please run `pip install -e cli/` to install CLI dependencies.');
      process.exit(1);
    }

    // 3. Python Schema Generation
    console.log('🐍 Generating CLI schema from Python models...');
    execSync(`PYTHONPATH=cli ${pythonCmd} cli/dev_tools/schema_gen.py`, {
      stdio: 'inherit',
      env: { ...process.env, PYTHONPATH: 'cli' }
    });

    // 4. Sync Contracts
    console.log('🔄 Syncing contracts...');
    execSync('pnpm --filter @arii/boomtick-mcp exec tsx scripts/sync-contracts.ts', { stdio: 'inherit' });

    // 5. Sync MCP Schemas
    console.log('🛠️  Syncing MCP schemas...');
    execSync('pnpm --filter @arii/boomtick-mcp run sync:mcp-schemas', { stdio: 'inherit' });

    // 6. Generation complete
    console.log('📊 Schema/contract generation complete.');

    console.log('\n✅ Schema verification complete.');
  } catch (err) {
    console.error('\n❌ Verification failed due to an error in the sub-tasks:', err);
    process.exit(1);
  }
}

verifySchemas();
