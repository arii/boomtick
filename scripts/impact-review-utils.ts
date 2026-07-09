import { spawn, type ChildProcess } from 'child_process';
import fs from 'fs';
import path from 'path';

export interface ImpactAnalysisArtifact {
  routes?: string[];
  visualReviewRequired?: string[];
  changedFiles?: string[];
  affectedPages?: string[];
  impactLevel?: 'HIGH' | 'MEDIUM' | 'LOW';
}

export interface LayoutMetrics {
  scrollWidth: number;
  clientWidth: number;
  mainWidth: number;
  scrollHeight: number;
  viewportWidth: number;
}

export interface LayoutValidation {
  passed: boolean;
  reason?: string;
}

export interface VisualRouteSummary {
  route: string;
  slug: string;
  suffix: string;
  beforePath: string;
  afterPath: string;
  diffPath: string;
  beforeCroppedPath?: string;
  afterCroppedPath?: string;
  diffCroppedPath?: string;
  diffPixels: number;
  totalPixels: number;
  differencePercent: number;
  severity: 'LOW' | 'MEDIUM' | 'HIGH';
  metrics?: {
    before: LayoutMetrics;
    after: LayoutMetrics;
  };
  validation?: LayoutValidation;
}

export interface VisualSummary {
  routes: VisualRouteSummary[];
}

export interface DomRouteSummary {
  route: string;
  slug: string;
  beforeHtmlPath: string;
  afterHtmlPath: string;
  diffPath: string;
  structureDiffPath: string;
  metrics: {
    nodesAdded: number;
    nodesRemoved: number;
    imagesAdded: number;
    imagesRemoved: number;
    linksAdded: number;
    linksRemoved: number;
  };
  severity: 'LOW' | 'MEDIUM' | 'HIGH';
}

export const ARTIFACTS_DIR = path.join(process.cwd(), 'artifacts');
export const VISUAL_REVIEW_DIR = path.join(ARTIFACTS_DIR, 'visual-review');
export const DOM_REVIEW_DIR = path.join(ARTIFACTS_DIR, 'dom-review');
export const IMPACT_ANALYSIS_PATH = path.join(ARTIFACTS_DIR, 'impact-analysis.json');
export const VISUAL_SUMMARY_PATH = path.join(VISUAL_REVIEW_DIR, 'summary.json');
export const DOM_SUMMARY_PATH = path.join(DOM_REVIEW_DIR, 'summary.json');

import { IMPACT_CONFIG } from './impact-analysis.config';

/**
 * Maps page component files to authoritative sitemap URLs.
 */
export function mapPageToUrls(filePath: string, sitemapUrls: string[]): string[] {
  const fileName = path.basename(filePath, path.extname(filePath));

  let routePattern = `/${fileName.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase()}`;
  if (IMPACT_CONFIG.PAGE_ROUTE_OVERRIDES[fileName]) {
    routePattern = IMPACT_CONFIG.PAGE_ROUTE_OVERRIDES[fileName];
  }

  if (routePattern === '/') {
    return sitemapUrls.includes('/') ? ['/'] : [];
  }

  // Convert dynamic routes like /blog/:slug to a prefix /blog/
  const staticPrefixMatch = routePattern.match(/^(\/[a-z0-9-]+)\/:[a-zA-Z0-9_]+$/);

  if (staticPrefixMatch) {
    const prefix = `${staticPrefixMatch[1]}/`;
    return sitemapUrls.filter(url => url.startsWith(prefix) && url !== staticPrefixMatch[1]);
  }

  // Exact match
  if (sitemapUrls.includes(routePattern)) {
    return [routePattern];
  }

  // Fallback for when the exact pattern isn't in sitemap and it's not a known prefix route.
  // This avoids running impact analysis on nonexistent pages.
  console.warn(`[Impact Analysis] Warning: Route pattern '${routePattern}' derived from '${filePath}' was not found in the authoritative sitemap.`);
  return [];
}

export function ensureDirectory(directory: string): void {
  fs.mkdirSync(directory, { recursive: true });
}

export function routeToSlug(route: string): string {
  if (route === '/') return 'home';

  const withoutQuery = route.split('?')[0] ?? route;
  const slug = withoutQuery
    .replace(/^\/+|\/+$/g, '')
    .replace(/[:*]/g, '')
    .replace(/[^a-zA-Z0-9-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase();

  return slug || 'home';
}

export function readImpactAnalysis(): Required<Pick<ImpactAnalysisArtifact, 'routes'>> & ImpactAnalysisArtifact {
  const candidates = [
    IMPACT_ANALYSIS_PATH,
    path.join(ARTIFACTS_DIR, 'impact-analysis', 'impact.json')
  ];

  const artifactPath = candidates.find(candidate => fs.existsSync(candidate));
  if (!artifactPath) {
    throw new Error('Missing impact analysis artifact. Run `pnpm impact:analysis` first.');
  }

  const artifact = JSON.parse(fs.readFileSync(artifactPath, 'utf8')) as ImpactAnalysisArtifact;
  const routes = artifact.routes ?? artifact.visualReviewRequired ?? [];

  return { ...artifact, routes };
}

export function visualSeverity(percent: number): 'LOW' | 'MEDIUM' | 'HIGH' {
  // Threshold should align with VISUAL_DIFF_THRESHOLD env var.
  // Default failure is 1.5%. We set MEDIUM to start at 2/3 of failure threshold.
  const failThreshold = Number(process.env.VISUAL_DIFF_THRESHOLD) || 1.5;
  const mediumThreshold = failThreshold * 0.66;

  if (percent > 5) return 'HIGH';
  if (percent > mediumThreshold) return 'MEDIUM';
  return 'LOW';
}

export function domSeverity(nodesChanged: number): 'LOW' | 'MEDIUM' | 'HIGH' {
  if (nodesChanged > 20) return 'HIGH';
  if (nodesChanged > 5) return 'MEDIUM';
  return 'LOW';
}

export function combinedSeverity(...severities: Array<'LOW' | 'MEDIUM' | 'HIGH' | undefined>): 'LOW' | 'MEDIUM' | 'HIGH' {
  if (severities.includes('HIGH')) return 'HIGH';
  if (severities.includes('MEDIUM')) return 'MEDIUM';
  return 'LOW';
}

export function startPreview(cwd: string, port: number): ChildProcess {
  const child = spawn('pnpm', ['exec', 'vite', 'preview', '--host', '127.0.0.1', '--port', String(port)], {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      VITE_BASE_PATH: '/'
    }
  });

  child.stdout?.on('data', data => process.stdout.write(`[preview:${port}] ${String(data)}`));
  child.stderr?.on('data', data => process.stderr.write(`[preview:${port}] ${String(data)}`));

  return child;
}

export async function waitForServer(url: string, timeoutMs = 30_000): Promise<void> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok || response.status < 500) return;
    } catch {
      // Retry until timeout.
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }

  throw new Error(`Timed out waiting for ${url}`);
}

export function stopPreview(child: ChildProcess): void {
  if (!child.killed) {
    child.kill('SIGTERM');
  }
}
