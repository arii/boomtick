import { readFile, access } from 'node:fs/promises';
import { VISUAL_SUMMARY_PATH, type VisualSummary, type VisualRouteSummary } from './impact-review-utils';

/**
 * Checks if a file exists asynchronously.
 */
async function fileExists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

/**
 * Validates the structure of the visual summary and counts routes with
 * a difference percent greater than the 1.5% threshold.
 */
async function getSignificantVisualChangeCount(): Promise<number> {
  if (!(await fileExists(VISUAL_SUMMARY_PATH))) {
    console.warn(`[check-visual-changes] Warning: Visual summary file not found at ${VISUAL_SUMMARY_PATH}. Defaulting to 0.`);
    return 0;
  }

  try {
    const content = await readFile(VISUAL_SUMMARY_PATH, 'utf-8');
    const summary = JSON.parse(content) as VisualSummary;

    if (!summary || typeof summary !== 'object' || !Array.isArray(summary.routes)) {
      console.error('[check-visual-changes] Error: Invalid visual summary format. Expected { routes: [...] }');
      return 0;
    }

    const threshold = Number(process.env.VISUAL_DIFF_THRESHOLD) || 1.5;
    const significantChanges = summary.routes.filter((route: VisualRouteSummary) => {
      if (!route || typeof route.differencePercent !== 'number') {
        console.warn(`[check-visual-changes] Warning: Skipping route entry with missing or non-numeric differencePercent: ${JSON.stringify(route)}`);
        return false;
      }
      return route.differencePercent > threshold;
    });

    if (significantChanges.length > 0) {
      console.error(`❌ [check-visual-changes] Found ${significantChanges.length} routes with visual changes exceeding the ${threshold}% threshold.`);
      significantChanges.forEach(r => {
        console.error(`   - ${r.route}: ${r.differencePercent.toFixed(2)}% difference`);
      });
    }

    return significantChanges.length;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const context = error instanceof SyntaxError ? ` Content: ${await readFile(VISUAL_SUMMARY_PATH, 'utf-8').catch(() => 'unavailable')}` : '';
    console.error(`[check-visual-changes] Error processing visual summary: ${message}${context}`);
    return 0;
  }
}

async function main() {
  try {
    const count = await getSignificantVisualChangeCount();
    process.stdout.write(`changed_routes=${count}\n`);
  } catch (error) {
    console.error(`[check-visual-changes] Fatal error: ${error instanceof Error ? error.message : String(error)}`);
    process.stdout.write(`changed_routes=0\n`);
    process.exit(1);
  }
}

void main();
