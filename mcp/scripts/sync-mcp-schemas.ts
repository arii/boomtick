import * as fs from 'fs';
import * as path from 'path';
import { MCP_TOOLS } from '../src/mcp/definitions.js';

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

function syncSchemas() {
  console.log('🔄 Synchronizing MCP tool schemas...');

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

  MCP_TOOLS.forEach(tool => {
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

  console.log(`✅ Synchronized ${MCP_TOOLS.length} tool schemas to ${validTargets.length} locations.`);
  validTargets.forEach(target => console.log(`   - ${target}`));
}

try {
  syncSchemas();
} catch (error) {
  console.error('❌ Unexpected error during MCP schema synchronization:', error);
  process.exit(1);
}
