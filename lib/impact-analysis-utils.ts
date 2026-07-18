import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { IMPACT_CONFIG } from '../scripts/impact-analysis.config';
/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/no-require-imports */
// @ts-expect-error - May not exist in standalone boomtick
let getAllRoutes: any;
try {
  // @ts-expect-error - May not exist in standalone boomtick
  getAllRoutes = require('../../src/lib/routes-discovery').getAllRoutes;
} catch {
  getAllRoutes = () => ({ stubs: [] });
}
/* eslint-enable @typescript-eslint/no-explicit-any, @typescript-eslint/no-require-imports */
import { mapPageToUrls } from '../scripts/impact-review-utils';
import { loadProjectConfig } from './projectConfig';

// Types for dependency-cruiser output
export interface Dependency {
  resolved: string;
  dynamic?: boolean;
  module?: string;
  dependencyTypes?: string[];
}

export interface Module {
  source: string;
  dependencies: Dependency[];
}

export interface DependencyGraph {
  modules: Module[];
  summary?: Record<string, unknown>;
}

export interface ReverseDependency {
  source: string;
  dynamic: boolean;
}

export interface ImpactReport {
  changedFiles: string[];
  affectedPages: string[];
  affectedDynamicImports: string[];
  routes: string[];
  visualReviewRequired: string[];
  impactLevel: 'HIGH' | 'MEDIUM' | 'LOW';
  sharedLayouts?: string[];
  layoutTrace?: Record<string, string[]>;
}

/**
 * Checks if a given file path represents a layout file.
 */
export function isLayoutFile(filePath: string): boolean {
  return filePath.startsWith('src/layouts/') || /Layout\.[jt]sx?$/i.test(filePath);
}

/**
 * Sanitizes and validates a file path to prevent path traversal and restrict execution
 * to valid, localized workspace files.
 * Rejects absolute paths, protocols, or path traversal sequences containing "..".
 *
 * @param filePath The file path to validate.
 */
export function sanitizeFilePath(filePath: unknown): string | null {
  if (typeof filePath !== 'string' || !filePath.trim()) {
    return null;
  }
  const cleanPath = filePath.trim();
  if (path.isAbsolute(cleanPath) || cleanPath.includes('..') || cleanPath.startsWith('/') || cleanPath.includes('\0')) {
    return null;
  }
  // Reject URLs/protocols or backslashes
  if (cleanPath.includes('://') || cleanPath.includes('\\')) {
    return null;
  }
  return cleanPath;
}

/**
 * Options to customize the behavior of the dependency graph traversal.
 */
export interface TraversalOptions {
  /**
   * If true, the traversal along a path stops immediately when a match is found
   * (meaning we record the matching file but do not enqueue its ancestors).
   */
  stopAtMatch?: boolean;
  /**
   * Optional callback function invoked when a match is discovered during traversal.
   * Useful for separating traversal logic from custom side-effects (e.g., logging).
   */
  onMatch?: (current: string, matched: string) => void;
}

/**
 * Traverses the reverse dependency graph starting from a set of files using an optimized BFS.
 * Implements strict O(V + E) time complexity with O(1) constant array queue operations using a pointer.
 * Defensive against malformed inputs and prevents infinite loops caused by circular dependencies.
 *
 * @param startFiles List of files to begin traversal from.
 * @param reverseMap The reverse dependency map (child -> parents).
 * @param predicate A callback function to determine if a visited parent should be collected.
 * @param options Traversal options to customize BFS behavior.
 */
export function traverseDependencyGraph(
  startFiles: string[],
  reverseMap: Record<string, ReverseDependency[]>,
  predicate: (filePath: string) => boolean,
  options: TraversalOptions = {}
): {
  tracePaths: Record<string, string[]>;
  collected: string[];
} {
  // Defensive type validation on reverseMap
  if (!reverseMap || typeof reverseMap !== 'object') {
    return { tracePaths: {}, collected: [] };
  }

  const tracePaths: Record<string, string[]> = {};
  const collectedSet = new Set<string>();
  const MAX_ITERATIONS = 50000;
  let iterations = 0;

  for (const file of startFiles) {
    if (typeof file !== 'string') continue;

    const trace: string[] = [];
    const queue: string[] = [file];
    const visited = new Set<string>([file]);

    let head = 0;
    while (head < queue.length) {
      iterations++;
      if (iterations > MAX_ITERATIONS) {
        throw new Error(`❌ Infinite loop safety limit exceeded (${MAX_ITERATIONS} iterations) during dependency graph traversal.`);
      }

      const current = queue[head++];
      const parents = reverseMap[current];

      // Validate parent collection structure safely
      if (!Array.isArray(parents)) continue;

      for (const parent of parents) {
        if (!parent || typeof parent !== 'object' || typeof parent.source !== 'string') {
          continue;
        }

        if (!visited.has(parent.source)) {
          visited.add(parent.source);

          const isMatch = predicate(parent.source);
          if (isMatch) {
            trace.push(parent.source);
            collectedSet.add(parent.source);
            if (options.onMatch) {
              options.onMatch(current, parent.source);
            }
          }

          // Decide if we should continue queueing parents along this path
          const shouldEnqueue = !isMatch || !options.stopAtMatch;
          if (shouldEnqueue) {
            queue.push(parent.source);
          }
        }
      }
    }

    if (trace.length > 0) {
      tracePaths[file] = trace;
    }
  }

  return {
    tracePaths,
    collected: Array.from(collectedSet).sort()
  };
}

/**
 * Traverses the layout hierarchy upward starting from each point of change detection.
 * If a changed file is a layout, or if it eventually affects a layout, it traces
 * any parent/ancestor layout files recursively through standard/static imports in the
 * reverse dependency map.
 *
 * Rejects and filters out any untrusted or invalid file paths to prevent path traversal risks.
 *
 * @param changedFiles List of changed files detected.
 * @param reverseMap The reverse dependency map (child -> parents).
 */
export function traceLayoutHierarchyUpward(
  changedFiles: string[],
  reverseMap: Record<string, ReverseDependency[]>
): {
  layoutTrace: Record<string, string[]>;
  sharedLayouts: string[];
} {
  // 1. Sanitize and validate inputs
  const sanitizedFiles: string[] = [];
  for (const file of changedFiles) {
    const clean = sanitizeFilePath(file);
    if (clean) {
      sanitizedFiles.push(clean);
    }
  }

  const directLayouts = sanitizedFiles.filter(isLayoutFile);
  const nonLayouts = sanitizedFiles.filter(file => !isLayoutFile(file));

  // Defined callback for decoupled, structured logging
  const logMatch = (current: string, matched: string) => {
    console.log(`🔄 [Layout Hierarchy] Shared layout change detected: "${matched}" is affected by component/layout "${current}"`);
  };

  // 2. Locate layout entry points for non-layout files first
  const entryResult = traverseDependencyGraph(nonLayouts, reverseMap, isLayoutFile, { stopAtMatch: true });

  // 3. Union direct layout changes and transitive layout entry points to avoid redundant traversals
  const uniqueLayoutEntryPoints = Array.from(new Set([...directLayouts, ...entryResult.collected])).sort();

  // 4. Run a single unified BFS traversal upward from unique layout entry points
  const traceResult = traverseDependencyGraph(uniqueLayoutEntryPoints, reverseMap, isLayoutFile, { onMatch: logMatch });

  return {
    layoutTrace: traceResult.tracePaths,
    sharedLayouts: traceResult.collected
  };
}

/**
 * Executes a shell command and returns the output.
 */
export function exec(command: string): string {
  try {
    return execSync(command, {
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'pipe'],
      maxBuffer: IMPACT_CONFIG.MAX_BUFFER
    }).trim();
  } catch (error: unknown) {
    const err = error as { stderr?: string; message?: string };
    throw new Error(`Command failed: ${command}\n${err.stderr || err.message}`, { cause: error });
  }
}

/**
 * Helper to split string into lines and filter empty values.
 */
const splitAndFilter = (output: string): string[] => (output ? output.split('\n').filter(Boolean) : []);

/**
 * Gets the list of changed files between current HEAD and origin/main.
 * Falls back to HEAD~1 if origin/main is not available.
 */
export function getChangedFiles(): string[] {
  // Check for staged and unstaged changes first
  const staged = exec('git diff --name-only --cached');
  const unstaged = exec('git diff --name-only');
  const workingChanges = new Set([...splitAndFilter(staged), ...splitAndFilter(unstaged)]);

  const config = loadProjectConfig();
  let base = config.base_branch;
  try {
    execSync(`git rev-parse ${base}`, { stdio: 'ignore' });
  } catch {
    try {
      execSync('git rev-parse HEAD~1', { stdio: 'ignore' });
      base = 'HEAD~1';
    } catch {
      // Use empty tree hash if no previous commit exists
      base = exec('git hash-object -t tree /dev/null');
    }
  }

  const committed = exec(`git diff --name-only ${base} HEAD`);
  const allChanges = new Set([...workingChanges, ...splitAndFilter(committed)]);

  return Array.from(allChanges).filter(Boolean);
}

/**
 * Builds a reverse dependency map (child -> [parents]).
 */
export function buildReverseMap(graph: DependencyGraph): Record<string, ReverseDependency[]> {
  const reverseMap: Record<string, ReverseDependency[]> = {};

  graph.modules.forEach(module => {
    module.dependencies.forEach(dep => {
      const child = dep.resolved;
      if (!child) return;

      if (!reverseMap[child]) {
        reverseMap[child] = [];
      }

      if (!reverseMap[child].some(rd => rd.source === module.source)) {
        reverseMap[child].push({
          source: module.source,
          dynamic: !!dep.dynamic
        });
      }
    });
  });

  return reverseMap;
}

/**
 * Recursively finds all affected files starting from the changed files using BFS.
 *
 * Note: While dependency-cruiser provides reachability analysis, we perform a manual
 * traversal here to gain granular control over the 'dynamic' vs 'static' dependency
 * links.
 *
 * RATIONALE:
 * In modern code-split React apps, every page is often dynamically imported by the
 * router. If we treated these dynamic imports as standard dependencies, every change
 * to any page would "reach" the router (src/config/routes.ts). Since the router is a
 * "Global Trigger", this would cause every single change to flag a high-severity
 * Global Impact, requiring visual review of the entire site.
 *
 * By distinguishing between static and dynamic links, we can:
 * 1. Traverse dynamic links to find which routes are affected (Route Discovery).
 * 2. Ignore dynamic links when checking if a change affects a global layout or
 *    the app core (Global Impact Gating).
 */
export function findAffectedFiles(
  changedFiles: string[],
  reverseMap: Record<string, ReverseDependency[]>,
  options: { includeDynamic: boolean } = { includeDynamic: true }
): string[] {
  const affected = new Set<string>();
  const queue = [...changedFiles];

  for (const file of queue) {
    affected.add(file);
  }

  while (queue.length > 0) {
    const file = queue.shift()!;

    const parents = reverseMap[file] || [];
    for (const parent of parents) {
      if (options.includeDynamic || !parent.dynamic) {
        if (!affected.has(parent.source)) {
          affected.add(parent.source);
          queue.push(parent.source);
        }
      }
    }
  }

  return Array.from(affected);
}

/**
 * Maps resolved file paths to their application routes by analyzing the router configuration.
 */
export function getDynamicRouteMapping(graph: DependencyGraph): Record<string, string> {
  const mapping: Record<string, string> = {};
  const routesModule = graph.modules.find(m => m.source === 'src/config/routes.ts');
  if (!routesModule) return mapping;

  const routesFilePath = 'src/config/routes.ts';
  if (!fs.existsSync(routesFilePath)) return mapping;

  const routesContent = fs.readFileSync(routesFilePath, 'utf-8');
  const routeConfigs = routesContent.split(/\{[\s\n]*path:/);

  routesModule.dependencies.forEach(dep => {
    if (dep.dynamic && dep.resolved) {
      const modulePath = dep.module || '';
      if (!modulePath) return;

      const escapedModule = modulePath.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const moduleRegex = new RegExp(`import\\(['"]${escapedModule}['"]\\)`);

      for (const config of routeConfigs) {
        if (moduleRegex.test(config)) {
          const pathMatch = config.match(/^\s*['"]([^'"]+)['"]/);
          if (pathMatch && pathMatch[1]) {
            mapping[dep.resolved] = pathMatch[1];
            break;
          }
        }
      }
    }
  });

  return mapping;
}

/**
 * Resolves the list of affected URLs based on code, content, and public file changes.
 */
export function resolveAffectedUrls(
  allAffected: string[],
  changedFiles: string[],
  dynamicRouteMapping: Record<string, string>,
  staticAffected: string[]
): string[] {
  const pageComponentFiles = Object.keys(dynamicRouteMapping);
  const authoritativeSitemapUrls = getAllRoutes().stubs || [];

  const hasGlobalImpact = staticAffected.some(f => IMPACT_CONFIG.GLOBAL_TRIGGERS.includes(f));

  if (hasGlobalImpact) {
    console.log('🌍 Global impact detected (App, Routes, or MainLayout affected).');
    return IMPACT_CONFIG.DEFAULT_STATIC_PAGES;
  }

  const affectedPages = allAffected.filter(f =>
    f.startsWith(IMPACT_CONFIG.PAGES_DIR) || pageComponentFiles.includes(f)
  );

  const pageUrls = Array.from(new Set(affectedPages.flatMap(pageFile => {
    if (dynamicRouteMapping[pageFile]) {
      const routePattern = dynamicRouteMapping[pageFile];
      if (routePattern === '/') return authoritativeSitemapUrls.includes('/') ? ['/'] : [];

      const staticPrefixMatch = routePattern.match(/^(\/[a-z0-9-]+)\/:[a-zA-Z0-9_]+$/);
      if (staticPrefixMatch) {
        const prefix = `${staticPrefixMatch[1]}/`;
        return authoritativeSitemapUrls.filter(url => url.startsWith(prefix) && url !== staticPrefixMatch[1]);
      }

      if (authoritativeSitemapUrls.includes(routePattern)) return [routePattern];
    }
    return mapPageToUrls(pageFile, authoritativeSitemapUrls);
  })));

  const contentUrls = getContentAffectedUrls(changedFiles);
  const publicFileUrls = getAffectedUrlsByPublicFiles(changedFiles);

  return Array.from(new Set([...pageUrls, ...contentUrls, ...publicFileUrls])).sort();
}

/**
 * Handles content changes and maps them to URLs.
 */
function getContentAffectedUrls(changedFiles: string[]): string[] {
  const urls: string[] = [];
  for (const file of changedFiles) {
    for (const [dir, prefix] of Object.entries(IMPACT_CONFIG.CONTENT_MAP)) {
      if (file.startsWith(dir) && file.endsWith('.md')) {
        // Only include files that still exist (avoid 404s in visual diff for deleted files)
        if (fs.existsSync(path.resolve(process.cwd(), file))) {
          const slug = path.basename(file, '.md');
          urls.push(`${prefix}${slug}`);
        }
      }
    }
  }
  return urls;
}

/**
 * Find affected markdown files when public static files (e.g. images) are changed.
 */
function getAffectedUrlsByPublicFiles(changedFiles: string[]): string[] {
  const urls: Set<string> = new Set();
  const publicFiles = changedFiles.filter(f => f.startsWith('public/'));
  if (publicFiles.length === 0) return [];

  const searchStrings = publicFiles.map(f => f.replace(/^public/, ''));

  for (const [dir, prefix] of Object.entries(IMPACT_CONFIG.CONTENT_MAP)) {
    const mdFiles = exec(`find ${dir} -name "*.md"`).split('\n').filter(Boolean);
    for (const mdFile of mdFiles) {
      const content = fs.readFileSync(mdFile, 'utf-8');
      for (const searchStr of searchStrings) {
        if (content.includes(searchStr)) {
          const slug = path.basename(mdFile, '.md');
          urls.add(`${prefix}${slug}`);
          urls.add(prefix.replace(/\/$/, ''));
        }
      }
    }
  }
  return Array.from(urls);
}

/**
 * Generates and writes the impact analysis reports.
 */
export function generateReports(report: ImpactReport, changedFiles: string[], affectedDynamicImportsSet: string[]) {
  const outputDir = path.join(process.cwd(), 'artifacts', 'impact-analysis');
  if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true });

  fs.writeFileSync(path.join(outputDir, 'impact.json'), JSON.stringify(report, null, 2));
  fs.writeFileSync(path.join(process.cwd(), 'artifacts', 'impact-analysis.json'), JSON.stringify(report, null, 2));

  let baseUrl = process.env.VITE_APP_URL || 'https://boomtick.blog';
  if (process.env.GITHUB_PAGES_URL) {
    baseUrl = process.env.GITHUB_PAGES_URL.replace(/\/$/, '');
  } else if (process.env.GITHUB_REPOSITORY && process.env.GITHUB_REF_NAME) {
    const [owner, repoName] = process.env.GITHUB_REPOSITORY.split('/');
    baseUrl = `https://${owner}.github.io/${repoName}/${process.env.GITHUB_REF_NAME}`;
  }

  const severityEmoji = report.impactLevel === 'HIGH' ? '🔴' : report.impactLevel === 'MEDIUM' ? '🟡' : '🟢';
  const changedFilesList = changedFiles.map(f => `- ${f}`).join('\n');

  let sharedLayoutsContent = '';
  if (report.sharedLayouts && report.sharedLayouts.length > 0) {
    sharedLayoutsContent = `
<details>
<summary><b>🔄 Shared Layouts Affected (${report.sharedLayouts.length})</b></summary>

${report.sharedLayouts.map(l => `- ${l}`).join('\n')}
</details>
`;
  }

  let layoutTraceMarkdown = '';
  if (report.layoutTrace && Object.keys(report.layoutTrace).length > 0) {
    layoutTraceMarkdown = `
<details>
<summary><b>🗺️ Layout Dependency Trace</b></summary>

${Object.entries(report.layoutTrace).map(([file, trace]) => `**${file}** affects layout(s): ${trace.join(', ')}`).join('\n\n')}
</details>
`;
  }

  const markdown = `## ${severityEmoji} Deployment Impact Analysis

> **Impact Level:** ${report.impactLevel}

### 👁️ Visual Review Required
${report.routes.length > 0 ? report.routes.map((url: string) => `- [${url}](${baseUrl}${url})`).join('\n') : '_None detected (code-only change)_'}
${sharedLayoutsContent}${layoutTraceMarkdown}
<details>
<summary><b>📦 Dynamic Imports Affected (${affectedDynamicImportsSet.length})</b></summary>

${affectedDynamicImportsSet.length > 0 ? affectedDynamicImportsSet.map(f => `- ${f}`).join('\n') : '_None detected_'}
</details>

<details>
<summary><b>📝 Changed Files (${changedFiles.length})</b></summary>

${changedFilesList}
</details>

---
*Generated by Boomtick Impact Analyzer*
`;

  fs.writeFileSync(path.join(outputDir, 'impact.md'), markdown);
  console.log(`\n✅ Reports generated in ${outputDir}`);
}
