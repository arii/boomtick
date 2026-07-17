import * as fs from 'fs';
import * as path from 'path';
import { ARTIFACTS_DIR, VISUAL_SUMMARY_PATH, MAX_ROUTES_TO_REVIEW } from './visualReviewConstants';
import { generateMarkdownReport, postPRComment, countExistingReviews, getJulesSessionIdFromPR, sendJulesMessage, getPreviousReviewState } from './visualReviewUtils';
import type { RouteReview, VisualRouteSummary, VisualSummary, VisualReviewState } from './visualReviewTypes';
import { logReviewExecution } from './aiLogger';
export type AgentRole = 'CODE_REVIEW' | 'ACCESSIBILITY' | 'UX' | 'VISUAL_REGRESSION' | 'RESPONSIVE_LAYOUT';

export interface LLMClientStrategy {
  botName: string;
  reportTitle: string;
  botTagline: string;
  reportFileName: string;
  invokeReview: (summary: VisualRouteSummary, role?: AgentRole) => Promise<RouteReview>;
}

const MAX_REVIEWS_PER_PR = parseInt(process.env.MAX_AI_REVIEWS ?? '10', 10);

export async function orchestrateVisualReview(
  client: LLMClientStrategy,
  allReportTitles: string[] = []
): Promise<void> {
  const agentReportPath = path.join(ARTIFACTS_DIR, client.reportFileName);

  const existing = await countExistingReviews(allReportTitles);
  if (existing >= MAX_REVIEWS_PER_PR) {
    console.log(`⏭️  Skipping ${client.botName} — ${existing}/${MAX_REVIEWS_PER_PR} reviews already posted.`);
    fs.writeFileSync(
      agentReportPath,
      `## ${client.reportTitle}\n\nSkipped: review quota (${MAX_REVIEWS_PER_PR}) already met.\n`
    );
    const prevState = await getPreviousReviewState<VisualReviewState>(client.reportTitle);
    fs.writeFileSync(path.join(ARTIFACTS_DIR, `${client.reportFileName.replace('.md', '')}-verdict.json`), JSON.stringify({
      passed: true,
      highCount: 0,
      routes: [],
      llmVerdict: 'pass',
      state: prevState || { findings: [] }
    }, null, 2));
    return;
  }

  if (!fs.existsSync(VISUAL_SUMMARY_PATH)) {
    console.warn('⚠️  Skipping agent review — missing visual summary. Run pnpm impact:visual-diff first.');
    fs.writeFileSync(agentReportPath, `## ${client.reportTitle}\n\nSkipped: Missing visual summary.\n`);
    const prevState = await getPreviousReviewState<VisualReviewState>(client.reportTitle);
    fs.writeFileSync(path.join(ARTIFACTS_DIR, `${client.reportFileName.replace('.md', '')}-verdict.json`), JSON.stringify({
      passed: true,
      highCount: 0,
      routes: [],
      llmVerdict: 'pass',
      state: prevState || { findings: [] }
    }, null, 2));
    return;
  }

  const summary: VisualSummary = JSON.parse(fs.readFileSync(VISUAL_SUMMARY_PATH, 'utf8'));

  // Load previous state and handle auto-resolution
  const prevState = await getPreviousReviewState<VisualReviewState>(client.reportTitle);
  if (prevState?.findings && Array.isArray(prevState.findings)) {
    for (const routeSummary of summary.routes) {
      const relevantFindings = prevState.findings.filter(f => f.route === routeSummary.route);

      // Auto-resolution: if pixel diff is low, mark all previous findings for this route as resolved
      if (routeSummary.differencePercent < 1.5) {
        for (const finding of relevantFindings) {
          if (finding.status === 'open') {
            finding.status = 'resolved';
            finding.fixSummary = 'Jules response: pixel difference is now below threshold (1.5%).';
            console.log(`✅ Auto-resolved visual finding for ${routeSummary.route}: ${finding.issue}`);
          }
        }
      }

      routeSummary.previousFindings = relevantFindings;
    }
  }

  // Only review routes with actual visual changes
  // Limit to top N routes by difference percentage to manage costs
  let routesToReview = summary.routes
    .filter(r => r.differencePercent > 1.5)
    .sort((a, b) => b.differencePercent - a.differencePercent);

  const totalRoutes = routesToReview.length;
  if (routesToReview.length > MAX_ROUTES_TO_REVIEW) {
    console.log(`⚠️  Too many routes changed (${totalRoutes}). Limiting review to the top ${MAX_ROUTES_TO_REVIEW}.`);
    routesToReview = routesToReview.slice(0, MAX_ROUTES_TO_REVIEW);
  }

  if (routesToReview.length === 0) {
    console.log(`✅ No visual changes detected — skipping agent review.`);
    fs.writeFileSync(agentReportPath, `## ${client.reportTitle}\n\nNo visual changes detected.\n`);
    fs.writeFileSync(path.join(ARTIFACTS_DIR, `${client.reportFileName.replace('.md', '')}-verdict.json`), JSON.stringify({ passed: true, highCount: 0, routes: [], llmVerdict: 'pass', state: { findings: [] } }, null, 2));
    return;
  }

  console.log(`🤖 Reviewing ${routesToReview.length} route(s) with ${client.botName}...`);

  const CONCURRENCY_LIMIT = 2;
  const reviews: RouteReview[] = [];
  const roles: AgentRole[] = ['CODE_REVIEW', 'ACCESSIBILITY', 'UX', 'VISUAL_REGRESSION', 'RESPONSIVE_LAYOUT'];

  const taskQueue: (() => Promise<void>)[] = [];

  for (const route of routesToReview) {
    console.log(`  → ${route.route} (${route.severity}, ${route.differencePercent.toFixed(2)}%)`);

    // Execute all specialized agents for this route
    const routeReviews = await Promise.all(roles.map(async (role) => {
      console.log(`    → Agent: ${role}`);
      const start = Date.now();
      try {
        const review = await client.invokeReview(route, role);
        const durationMs = Date.now() - start;
        logReviewExecution('visual-review', review, durationMs, { route: route.route });
        return { ...review, role };
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.error(`❌ Error in ${role} visual review task:`, err);
        return {
          route: route.route,
          severity: 'LOW',
          differencePercent: route.differencePercent,
          feedback: `Error: failed to execute ${role} visual review. Details: ${errorMsg}`,
          tokens: 0, cost: 0, inputTokens: 0, outputTokens: 0, cacheTokens: 0, modelName: 'unknown',
          llmVerdict: 'warn', role, findings: []
        } as RouteReview;
      }
    }));

    reviews.push(...routeReviews);
  }

  const workers = Array.from({ length: Math.min(CONCURRENCY_LIMIT, taskQueue.length) }, async () => {
    while (taskQueue.length > 0) {
      const task = taskQueue.shift();
      if (task) await task();
    }
  });

  await Promise.all(workers);

  const report = generateMarkdownReport(reviews, client.botName, client.reportTitle, client.botTagline);

  // Write local report
  fs.writeFileSync(agentReportPath, report);
  console.log(`✅ Local report written to ${agentReportPath}`);

  // Collect all findings from all reviews and merge with previous state to avoid loss
  const currentFindings = reviews.flatMap(r => r.findings || []);
  const currentIds = new Set(currentFindings.map(f => f.id));

  const state: VisualReviewState = { findings: currentFindings };
  if (prevState?.findings) {
    const missingFindings = prevState.findings.filter(f => !currentIds.has(f.id));
    if (missingFindings.length > 0) {
      console.log(`♻️  Restoring ${missingFindings.length} visual findings for untouched routes.`);
      state.findings.push(...missingFindings);
    }
  }

  // Post to GitHub PR
  await postPRComment(report, client.reportTitle, state);

  // Write a structured result file alongside the markdown
  const hasBlockingIssues = reviews.some(r =>
    r.llmVerdict === 'fail' || (r.severity === 'HIGH' && r.llmVerdict !== 'pass')
  );

  // Also alert Jules if this PR is from a Jules session
  const julesSessionId = await getJulesSessionIdFromPR();
  if (julesSessionId) {
    const hasWarnings = reviews.some(r => r.llmVerdict === 'warn');
    const passFailMsg = hasBlockingIssues ? "FAIL ❌" : ((hasWarnings || reviews.length === 0) ? "NEUTRAL ⚪" : "PASS ✅");
    const highCount = reviews.filter(r => r.severity === 'HIGH').length;
    const medCount = reviews.filter(r => r.severity === 'MEDIUM').length;
    const lowCount = reviews.filter(r => r.severity === 'LOW').length;
    const julesMessage = `[${client.reportTitle}] posted a visual UI review (${passFailMsg}). Summary: 🔴 ${highCount} high · 🟡 ${medCount} medium · 🟢 ${lowCount} low. Please read the review comments on the PR, analyze the diff context provided, and fix any failed or warned areas.\n\n<details><summary>Overview</summary>\n\n${report}\n</details>`;
    await sendJulesMessage(julesSessionId, julesMessage);
  }

  const verdictPath = path.join(ARTIFACTS_DIR, `${client.reportFileName.replace('.md', '')}-verdict.json`);
  fs.writeFileSync(verdictPath, JSON.stringify({
    passed: !hasBlockingIssues,
    highCount: reviews.filter(r => r.severity === 'HIGH').length,
    routes: reviews.map(r => ({ route: r.route, severity: r.severity, llmVerdict: r.llmVerdict })),
    state: state || { findings: [] }
  }, null, 2));

  if (hasBlockingIssues) {
    console.error(`❌ Visual review found HIGH severity issues — failing CI.`);
    // We intentionally don't crash the script here to allow the review workflow to complete fully
    // process.exit(1);
  }
}
