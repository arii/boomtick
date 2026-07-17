// impeccable-ignore-file
import { chromium, type Browser } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { logHeartbeat } from '../lib/heartbeat';
import pixelmatch from 'pixelmatch';
import { PNG } from 'pngjs';
import sharp from 'sharp';
import {
  ARTIFACTS_DIR,
  DEFAULT_VIEWPORTS,
  DOM_REVIEW_DIR,
  VISUAL_REVIEW_DIR,
  VISUAL_SUMMARY_PATH,
  ensureDirectory,
  readImpactAnalysis,
  routeToSlug,
  startPreview,
  stopPreview,
  visualSeverity,
  waitForServer,
  type VisualRouteSummary,
  type LayoutMetrics,
  type LayoutValidation
} from './impact-review-utils';
import { whiteCanvas, copyImage } from './image-processing-utils.ts';

const basePort = Number(process.env.IMPACT_BASE_PORT ?? 4173);
const headPort = Number(process.env.IMPACT_HEAD_PORT ?? 4174);
const baseUrl = process.env.IMPACT_BASE_URL ?? `http://127.0.0.1:${basePort}`;
const headUrl = process.env.IMPACT_HEAD_URL ?? `http://127.0.0.1:${headPort}`;
const baseWorktree = process.env.IMPACT_BASE_WORKTREE ?? path.join(process.cwd(), '.tmp-main');
const DEFAULT_CROP_PADDING = Number(process.env.IMPACT_CROP_PADDING ?? 20);

interface BoundingBox {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

function calculateBoundingBox(before: PNG, after: PNG): BoundingBox | null {
  const width = Math.min(before.width, after.width);
  const height = Math.min(before.height, after.height);
  let minX = width;
  let minY = height;
  let maxX = 0;
  let maxY = 0;
  let found = false;

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = (width * y + x) << 2;

      const r1 = before.data[idx];
      const g1 = before.data[idx + 1];
      const b1 = before.data[idx + 2];
      const a1 = before.data[idx + 3];

      const r2 = after.data[idx];
      const g2 = after.data[idx + 1];
      const b2 = after.data[idx + 2];
      const a2 = after.data[idx + 3];

      if (r1 !== r2 || g1 !== g2 || b1 !== b2 || a1 !== a2) {
        found = true;
        if (x < minX) minX = x;
        if (y < minY) minY = y;
        if (x > maxX) maxX = x;
        if (y > maxY) maxY = y;
      }
    }
  }

  return found ? { minX, minY, maxX, maxY } : null;
}

async function cropImage(imagePath: string, outputPath: string, box: BoundingBox, padding = DEFAULT_CROP_PADDING): Promise<void> {
  const metadata = await sharp(imagePath).metadata();
  const width = metadata.width ?? 0;
  const height = metadata.height ?? 0;

  const left = Math.max(0, box.minX - padding);
  const top = Math.max(0, box.minY - padding);
  const extractWidth = Math.min(width - left, box.maxX - box.minX + 2 * padding);
  const extractHeight = Math.min(height - top, box.maxY - box.minY + 2 * padding);

  await sharp(imagePath)
    .extract({
      left: Math.floor(left),
      top: Math.floor(top),
      width: Math.floor(extractWidth),
      height: Math.floor(extractHeight)
    })
    .toFile(outputPath);
}

async function captureRoute(
  browser: Browser,
  base: string,
  route: string,
  imagePath: string,
  htmlPath: string,
  viewport = { width: 1440, height: 900 }
): Promise<LayoutMetrics> {
  const context = await browser.newContext({
    viewport,
    isMobile: viewport.width < 768,
    hasTouch: viewport.width < 768
  });

  const maxAttempts = 3;
  let lastError: any = null;

  try {
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const page = await context.newPage();
      try {
        const targetUrl = new URL(route, base).toString();
        // Wait for domcontentloaded, but set a reasonable timeout (e.g., 15s)
        await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 15_000 });

        // Custom wait: ensure body tag is available/loaded
        await page.waitForSelector('body', { state: 'attached', timeout: 5_000 });

        // Network idle wait is prone to timing out on external assets/analytics.
        // We set a short, graceful timeout (5s) and catch any timeout errors.
        await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => {
          console.warn(`[Impact Analysis] [Attempt ${attempt}] Warning: Network did not become idle for ${route} within 5s; continuing with current DOM state.`);
        });

        // Small pause to let any client-side layout stable/animations settle
        await page.waitForTimeout(500);

        const metrics = await page.evaluate((vpWidth: number) => {
          const main = document.querySelector('main');
          return {
            scrollWidth: document.body.scrollWidth,
            clientWidth: document.body.clientWidth,
            mainWidth: main ? main.clientWidth : 0,
            scrollHeight: document.body.scrollHeight,
            viewportWidth: vpWidth
          };
        }, viewport.width);

        await page.screenshot({ path: imagePath, fullPage: true });
        fs.writeFileSync(htmlPath, await page.content());
        return metrics;
      } catch (err) {
        lastError = err;
        console.warn(`⚠️ [Attempt ${attempt}/${maxAttempts}] Failed to capture route ${route}:`, err instanceof Error ? err.message : String(err));
        if (attempt < maxAttempts) {
          // Wait before retrying
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
      } finally {
        await page.close();
      }
    }
    // If we exhausted all attempts, throw the last error
    console.error(`❌ All ${maxAttempts} attempts to capture route ${route} failed.`);
    throw lastError;
  } finally {
    await context.close();
  }
}

function validateLayout(before: LayoutMetrics, after: LayoutMetrics): LayoutValidation {
  const viewportWidth = after.viewportWidth;

  if (after.mainWidth > 0 && after.mainWidth < viewportWidth * 0.5) {
    return { passed: false, reason: `Main content width (${after.mainWidth}px) is less than 50% of viewport (${viewportWidth}px).` };
  }

  const pageWidthChange = before.scrollWidth > 0 ? Math.abs(after.scrollWidth - before.scrollWidth) / before.scrollWidth : 0;
  if (pageWidthChange > 0.3) {
    return { passed: false, reason: `Page width changed significantly: ${(pageWidthChange * 100).toFixed(1)}% (Base: ${before.scrollWidth}px, PR: ${after.scrollWidth}px).` };
  }

  if (viewportWidth >= 1280 && after.mainWidth > 0 && after.mainWidth < 600) {
    return { passed: false, reason: `Largest container width (${after.mainWidth}px) is less than 600px on desktop.` };
  }

  return { passed: true };
}

async function captureViewport(
  baseBrowser: Browser,
  headBrowser: Browser,
  baseUrl: string,
  headUrl: string,
  route: string,
  slug: string,
  label: string,
  suffix: string,
  viewport: { width: number; height: number },
  routeVisualDir: string,
  routeDomDir: string
): Promise<VisualRouteSummary> {
  const beforePath = path.join(routeVisualDir, `before${suffix}.png`);
  const afterPath = path.join(routeVisualDir, `after${suffix}.png`);
  const diffPath = path.join(routeVisualDir, `diff${suffix}.png`);
  // Use unique directories for DOM captures to match how dom-diff and review clients expect them
  const beforeHtmlPath = path.join(routeDomDir, `before${suffix}.html`);
  const afterHtmlPath = path.join(routeDomDir, `after${suffix}.html`);

  console.log(`📸 Capturing ${route} (${label})`);
  const [beforeMetrics, afterMetrics] = await Promise.all([
    captureRoute(baseBrowser, baseUrl, route, beforePath, beforeHtmlPath, viewport),
    captureRoute(headBrowser, headUrl, route, afterPath, afterHtmlPath, viewport)
  ]);

  const validation = validateLayout(beforeMetrics, afterMetrics);
  if (!validation.passed) {
    console.error(`❌ Layout validation failed for ${route} (${label}): ${validation.reason}`);
  }

  const { before, after, ...diffMetrics } = createVisualDiff(beforePath, afterPath, diffPath);
  const boundingBox = calculateBoundingBox(before, after);

  let beforeCroppedPath: string | undefined;
  let afterCroppedPath: string | undefined;
  let diffCroppedPath: string | undefined;

  if (boundingBox) {
    const routeCroppedDir = path.join(routeVisualDir, `cropped${suffix}`);
    ensureDirectory(routeCroppedDir);

    const bcp = path.join(routeCroppedDir, 'before.png');
    const acp = path.join(routeCroppedDir, 'after.png');
    const dcp = path.join(routeCroppedDir, 'diff.png');

    console.log(`✂️  Cropping changes for ${route} (${label})`);
    await Promise.all([
      cropImage(beforePath, bcp, boundingBox),
      cropImage(afterPath, acp, boundingBox),
      cropImage(diffPath, dcp, boundingBox)
    ]);

    beforeCroppedPath = path.relative(process.cwd(), bcp);
    afterCroppedPath = path.relative(process.cwd(), acp);
    diffCroppedPath = path.relative(process.cwd(), dcp);
  }

  return {
    route: suffix ? `${route} (${label.toLowerCase()})` : route,
    slug,
    suffix,
    beforePath: path.relative(process.cwd(), beforePath),
    afterPath: path.relative(process.cwd(), afterPath),
    diffPath: path.relative(process.cwd(), diffPath),
    beforeCroppedPath,
    afterCroppedPath,
    diffCroppedPath,
    ...diffMetrics,
    severity: validation.passed ? visualSeverity(diffMetrics.differencePercent) : 'HIGH',
    metrics: { before: beforeMetrics, after: afterMetrics },
    validation
  };
}

function createVisualDiff(beforePath: string, afterPath: string, diffPath: string): { diffPixels: number; totalPixels: number; differencePercent: number; before: PNG; after: PNG } {
  const beforeRaw = PNG.sync.read(fs.readFileSync(beforePath));
  const afterRaw = PNG.sync.read(fs.readFileSync(afterPath));
  const width = Math.max(beforeRaw.width, afterRaw.width);
  const height = Math.max(beforeRaw.height, afterRaw.height);
  const before = whiteCanvas(width, height);
  const after = whiteCanvas(width, height);
  const diff = whiteCanvas(width, height);

  copyImage(beforeRaw, before);
  copyImage(afterRaw, after);

  const diffPixels = pixelmatch(before.data, after.data, diff.data, width, height, { threshold: 0.1 });
  const totalPixels = width * height;
  const differencePercent = totalPixels === 0 ? 0 : (diffPixels / totalPixels) * 100;

  fs.writeFileSync(diffPath, PNG.sync.write(diff));

  return { diffPixels, totalPixels, differencePercent, before, after };
}

async function main(): Promise<void> {
  await logHeartbeat('Starting Visual Diff');

  let viewports = DEFAULT_VIEWPORTS;
  try {
    // Try to load project-specific viewports if they exist
    // We use a dynamic import/require pattern to avoid compile-time failure in standalone boomtick
    const viewportPath = path.resolve(process.cwd(), 'src/constants/visual-viewports.ts');
    if (fs.existsSync(viewportPath)) {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const customViewports = require(viewportPath).VIEWPORTS;
      if (Array.isArray(customViewports)) {
        viewports = customViewports;
      }
    }
  } catch (err) {
    console.warn('⚠️  Could not load custom viewports, using defaults:', (err as Error).message);
  }

  let impact;
  try {
    impact = readImpactAnalysis();
  } catch (err) {
    console.warn(`⚠️ Skipping visual diff: ${(err as Error).message}`);
    return;
  }

  const routes = impact.routes.filter(route => !route.includes(':'));

  ensureDirectory(ARTIFACTS_DIR);
  ensureDirectory(VISUAL_REVIEW_DIR);
  ensureDirectory(DOM_REVIEW_DIR);

  if (routes.length === 0) {
    fs.writeFileSync(VISUAL_SUMMARY_PATH, JSON.stringify({ routes: [] }, null, 2));
    console.log('✅ No concrete routes require visual review.');
    return;
  }

  if (!fs.existsSync(path.join(baseWorktree, 'dist'))) {
    console.warn('⚠️ Missing built base worktree dist. Skipping visual diff.');
    return;
  }

  if (!fs.existsSync(path.join(process.cwd(), 'dist'))) {
    console.warn('⚠️ Missing PR dist. Skipping visual diff.');
    return;
  }

  const basePreview = startPreview(baseWorktree, basePort);
  const headPreview = startPreview(process.cwd(), headPort);

  const rawConcurrency = process.env.IMPACT_CONCURRENCY ? parseInt(process.env.IMPACT_CONCURRENCY, 10) : 3;
  const CONCURRENCY = isNaN(rawConcurrency) || rawConcurrency < 1 ? 3 : Math.min(rawConcurrency, 10);

  try {
    await Promise.all([waitForServer(baseUrl), waitForServer(headUrl)]);

    const baseBrowser = await chromium.launch();
    const headBrowser = await chromium.launch();

    const summaries: VisualRouteSummary[] = [];
    try {
      const tasks: (() => Promise<void>)[] = [];

      for (const route of routes) {
        const slug = routeToSlug(route);
        const routeVisualDir = path.join(VISUAL_REVIEW_DIR, slug);
        ensureDirectory(routeVisualDir);

        for (const vp of viewports) {
          const vpSlug = `${slug}-${vp.name.toLowerCase()}`;
          const vpDomDir = path.join(DOM_REVIEW_DIR, vpSlug);
          ensureDirectory(vpDomDir);

          tasks.push(async () => {
            const summary = await captureViewport(
              baseBrowser, headBrowser, baseUrl, headUrl, route, vpSlug, vp.name, vp.suffix,
              { width: vp.width, height: vp.height }, routeVisualDir, vpDomDir
            );
            summaries.push(summary);
          });
        }
      }

      // Run tasks with concurrency limit
      for (let i = 0; i < tasks.length; i += CONCURRENCY) {
        const batch = tasks.slice(i, i + CONCURRENCY);
        await Promise.all(batch.map(task => task()));
      }
    } finally {
      await Promise.all([baseBrowser.close(), headBrowser.close()]);
    }

    fs.writeFileSync(VISUAL_SUMMARY_PATH, JSON.stringify({ routes: summaries }, null, 2));
    console.log(`✅ Visual diffs generated in ${VISUAL_REVIEW_DIR}`);
    await logHeartbeat('Visual Diff Complete');

    const failedLayouts = summaries.filter(s => s.validation && !s.validation.passed);
    if (failedLayouts.length > 0) {
      console.error(`❌ Visual regression detected by automated measurements in ${failedLayouts.length} route(s).`);
      try {
        execSync('node scripts/detect-antipatterns.mjs', { stdio: 'inherit' });
      } catch {
        console.error('❌ Anti-pattern validation failed during visual review phase.');
      }
      process.exit(1);
    }
  } finally {
    stopPreview(basePreview);
    stopPreview(headPreview);
  }
}

main().catch(error => {
  console.error(`❌ Visual diff failed: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
