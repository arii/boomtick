import * as fs from 'fs';
import * as path from 'path';

const homeDir = process.env.HOME || process.env.USERPROFILE || '';
const globalTargetDir = homeDir ? path.join(homeDir, '.gemini', 'antigravity-cli', 'mcp', 'boomtick-mcp') : null;
const projectTargetDir = path.join(process.cwd(), '.mcp', 'schemas');

function isWritable(dir: string): boolean {
  try {
    const testFile = path.join(dir, '.write_test');
    fs.writeFileSync(testFile, '');
    fs.unlinkSync(testFile);
    return true;
  } catch {
    return false;
  }
}

interface ToolDefinition {
  name: string;
  inputSchema: Record<string, unknown>;
}

/**
 * Synchronizes MCP tool schemas to target locations.
 */
async function syncSchemas() {
  console.log('🔄 Synchronizing MCP tool schemas...');

  let mcpToolsModule;
  try {
    mcpToolsModule = await import('../src/mcp/definitions.js');
  } catch (err: unknown) {
    const error = err as { code?: string; message?: string };
    if (error.code === 'ERR_MODULE_NOT_FOUND' || error.message?.includes('Cannot find package')) {
      console.error('❌ Error: MCP dependencies or source files not found.');
      console.error('   Please run `pnpm install` in the root directory.');
      process.exit(1);
    }
    throw err;
  }

  const mcpTools = mcpToolsModule.MCP_TOOLS as ToolDefinition[];

  const targets = [projectTargetDir];
  if (globalTargetDir) targets.push(globalTargetDir);

  const validTargets: string[] = [];

  targets.forEach(dir => {
    try {
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
        console.log(`📁 Created directory: ${dir}`);
      }
      if (isWritable(dir)) {
        validTargets.push(dir);
      } else {
        console.warn(`⚠️  Directory is not writable, skipping: ${dir}`);
      }
    } catch (err) {
      console.warn(`⚠️  Failed to prepare directory, skipping: ${dir}`, err);
    }
  });

  if (validTargets.length === 0) {
    console.warn('⚠️  No valid target directories available for schema synchronization.');
    return;
  }

  mcpTools.forEach((tool) => {
    const schemaContent = JSON.stringify(tool.inputSchema, null, 2);
    const fileName = `${tool.name}.json`;

    validTargets.forEach(targetDir => {
      const filePath = path.join(targetDir, fileName);
      try {
        fs.writeFileSync(filePath, schemaContent);
      } catch (err) {
        console.error(`❌ Failed to write schema to ${filePath}:`, err);
      }
    });
  });

  console.log(`✅ Synchronized ${mcpTools.length} tool schemas to ${validTargets.length} locations.`);
  validTargets.forEach(target => console.log(`   - ${target}`));
}

// Ensure execution is awaited and errors are caught
(async () => {
  try {
    await syncSchemas();
  } catch (error) {
    console.error('❌ Unexpected error during MCP schema synchronization:', error);
    process.exit(1);
  }
})();
