import * as fs from 'node:fs';
import * as path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const exec = promisify(execFile);

interface Module {
  source?: string;
  dependencies?: Array<{ resolved?: string }>;
}

export interface AIContextEntry {
  path: string;
  dependencies: string[];
  dependents: string[];
  semantic: Array<{ path: string; document: string }>;
}

function parseGraph(text: string): Module[] {
  const data: unknown = JSON.parse(text);
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error('Dependency graph must be an object');
  }
  const modules = (data as { modules?: unknown }).modules;
  if (modules === undefined) return [];
  if (!Array.isArray(modules)) throw new Error('Dependency graph modules must be an array');
  for (const module of modules) {
    if (!module || typeof module !== 'object' || Array.isArray(module)) throw new Error('Invalid graph module');
    if ('source' in module && typeof module.source !== 'string') throw new Error('Invalid module source');
    if ('dependencies' in module) {
      if (!Array.isArray(module.dependencies)) throw new Error('Invalid module dependencies');
      for (const dependency of module.dependencies) {
        if (!dependency || typeof dependency !== 'object' || Array.isArray(dependency)) throw new Error('Invalid dependency');
        if ('resolved' in dependency && typeof dependency.resolved !== 'string') throw new Error('Invalid resolved dependency');
      }
    }
  }
  return modules;
}

/** Native equivalent of the registered td ai get-context dependency contract. */
export async function getAIContext(inputData: string): Promise<AIContextEntry[]> {
  const input: unknown = JSON.parse(inputData);
  if (!input || typeof input !== 'object' || Array.isArray(input) || !('files' in input)) {
    throw new Error('Context input must be an object with files');
  }
  const files = (input as { files: unknown }).files;
  if (!Array.isArray(files)) throw new Error('Context files must be an array');
  if (files.length === 0) return [];
  for (const file of files) {
    if (!file || typeof file !== 'object' || typeof file.path !== 'string') throw new Error('Invalid context file');
  }

  const cachePath = path.join('artifacts', 'dependency-graph.json');
  let modules: Module[];
  if (fs.existsSync(cachePath)) {
    modules = parseGraph(await fs.promises.readFile(cachePath, 'utf8'));
  } else if (['.dependency-cruiser.config.mjs', 'tsconfig.app.json', 'src'].every(file => fs.existsSync(file))) {
    // The pure-Node image already installs this binary. Never download a fallback.
    const result = await exec('depcruise', [
      'src', '--config', '.dependency-cruiser.config.mjs',
      '--ts-config', 'tsconfig.app.json', '--output-type', 'json',
    ], { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024, timeout: 60_000 });
    modules = parseGraph(result.stdout);
  } else {
    console.warn('Dependency graph not applicable: missing config or src directory (registered CLI behavior).');
    modules = [];
  }

  const dependencies = new Map<string, string[]>();
  const dependents = new Map<string, string[]>();
  for (const module of modules) {
    if (module.source === undefined) continue;
    const resolved = (module.dependencies || []).flatMap(dependency => dependency.resolved === undefined ? [] : [dependency.resolved]);
    dependencies.set(module.source, resolved);
    for (const dependency of resolved) {
      dependents.set(dependency, [...(dependents.get(dependency) || []), module.source]);
    }
  }
  // The registered Python handler intentionally returns no semantic search hits.
  // Do not substitute lexical matches or claim vector retrieval occurred.
  return (files as Array<{ path: string }>).filter(file => file.path).map(file => ({
    path: file.path,
    dependencies: dependencies.get(file.path) || [],
    dependents: dependents.get(file.path) || [],
    semantic: [],
  }));
}
