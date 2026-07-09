import * as fs from 'fs';
import * as path from 'path';
import { IMPACT_CONFIG } from '../scripts/impact-analysis.config';
import { ARTIFACTS_DIR } from './visualReviewConstants';
import { postPRComment, countExistingReviews, getJulesSessionIdFromPR, sendJulesMessage, getPreviousReviewState } from './visualReviewUtils';
import { calculateEstimatedTokens, cleanupFeedback, batchFiles, calculateReviewHash, pruneCache, filterLowImpactFiles } from './codeReviewUtils';
import type { CodeReviewSummary, CodeReviewResult, CodeReviewState, CodeReviewRole } from './codeReviewTypes';
import { execFile as execFileCb, spawn } from 'child_process';
import { promisify } from 'util';
import { logReviewExecution } from './aiLogger';
import { loadProjectConfig } from './projectConfig';

const execFile = promisify(execFileCb);

const projectConfig = loadProjectConfig();
const MAX_DIFF_CHARS = projectConfig.max_diff_chars;

export interface CodeReviewClientStrategy {
  botName: string;
  reportTitle: string;
  botTagline: string;
  reportFileName: string;
  invokeReview: (summary: CodeReviewSummary, forceMaxOutputTokens?: number) => Promise<CodeReviewResult>;
}

const MAX_REVIEWS_PER_PR = parseInt(process.env.MAX_AI_REVIEWS ?? '10', 10);

function getInputComplexity(summary: CodeReviewSummary): number {
  return (summary.diffContext?.length ?? 0) + (summary.externalContext?.length ?? 0);
}

let cachedPRGoal: string | undefined | null = null;
async function fetchPRGoal(): Promise<string | undefined> {
  if (cachedPRGoal !== null) return cachedPRGoal;
  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPOSITORY;
  const prNumber = process.env.PR_NUMBER;
  if (!token || !repo || !prNumber) return undefined;

  try {
    const res = await fetch(`https://api.github.com/repos/${repo}/pulls/${prNumber}`, {
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
    });
    if (!res.ok) return undefined;
    const pr = await res.json() as { title: string; body: string | null };
    const body = pr.body?.trim() ? `\n\n${pr.body.trim()}` : '';
    cachedPRGoal = `${pr.title}${body}`;
    return cachedPRGoal;
  } catch {
    cachedPRGoal = undefined;
    return undefined;
  }
}

function parseImports(content: string): Map<string, string> {
  const imports = new Map<string, string>();
  const importRegex = /import\s+([\s\S]*?)\s+from\s+['"]([^'"]+)['"]/g;
  let match;
  while ((match = importRegex.exec(content)) !== null) {
    let symbolsPart = match[1].trim();
    const importPath = match[2];

    // Remove 'type ' prefix if it exists
    if (symbolsPart.startsWith('type ')) {
      symbolsPart = symbolsPart.slice(5).trim();
    }

    if (symbolsPart.includes('{')) {
      const curlyMatch = symbolsPart.match(/\{([\s\S]*?)\}/);
      if (curlyMatch) {
        const curlySymbols = curlyMatch[1].split(',');
        for (let s of curlySymbols) {
          s = s.trim();
          if (!s) continue;
          if (s.startsWith('type ')) {
            s = s.slice(5).trim();
          }
          const parts = s.split(/\s+as\s+/);
          const localName = parts[parts.length - 1].trim();
          imports.set(localName, importPath);
        }
      }
      const beforeCurlies = symbolsPart.split('{')[0].replace(/,/g, '').trim();
      if (beforeCurlies) {
        imports.set(beforeCurlies, importPath);
      }
    } else if (symbolsPart.includes('* as ')) {
      const parts = symbolsPart.split(/\s+as\s+/);
      const localName = parts[parts.length - 1].trim();
      imports.set(localName, importPath);
    } else if (symbolsPart) {
      imports.set(symbolsPart, importPath);
    }
  }
  return imports;
}

function escapeRegExp(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function resolveImportPath(importPath: string, currentFile: string): string | undefined {
  let resolvedPath: string;
  if (importPath.startsWith('@/')) {
    resolvedPath = path.join('src', importPath.slice(2));
  } else if (importPath.startsWith('.')) {
    resolvedPath = path.join(path.dirname(currentFile), importPath);
  } else {
    // Likely a node module, skip for now as we want project-specific interfaces
    return undefined;
  }

  const extensions = ['.tsx', '.ts', '.d.ts', '.jsx', '.js'];
  try {
    if (fs.existsSync(resolvedPath) && fs.lstatSync(resolvedPath).isFile()) {
      return resolvedPath;
    }

    for (const ext of extensions) {
      if (fs.existsSync(resolvedPath + ext)) {
        return resolvedPath + ext;
      }
    }

    for (const ext of extensions) {
      const indexPath = path.join(resolvedPath, 'index' + ext);
      if (fs.existsSync(indexPath)) {
        return indexPath;
      }
    }
  } catch {
    return undefined;
  }

  return undefined;
}

let cachedGitArgs: { diffArgs: string[], nameOnlyArgs: string[], contextBaseRef: string } | null = null;

async function getGitArgs(): Promise<{ diffArgs: string[], nameOnlyArgs: string[], contextBaseRef: string }> {
  if (cachedGitArgs) return cachedGitArgs;

  const baseRef = process.env.GITHUB_BASE_REF || projectConfig.base_branch;
  let diffArgs = ['diff', '-U10', `${baseRef}...HEAD`];
  let nameOnlyArgs = ['diff', '--name-only', `${baseRef}...HEAD`];
  let contextBaseRef = baseRef;

  try {
    await execFile('git', ['rev-parse', '--verify', baseRef]);
  } catch {
    try {
      await execFile('git', ['rev-parse', '--verify', 'main']);
      diffArgs = ['diff', '-U10', 'main...HEAD'];
      nameOnlyArgs = ['diff', '--name-only', 'main...HEAD'];
      contextBaseRef = 'main';
    } catch {
      diffArgs = ['diff', '-U10', 'HEAD~1', 'HEAD'];
      nameOnlyArgs = ['diff', '--name-only', 'HEAD~1', 'HEAD'];
      contextBaseRef = 'HEAD~1';
    }
  }

  cachedGitArgs = { diffArgs, nameOnlyArgs, contextBaseRef };
  return cachedGitArgs;
}

async function getAIContext(inputData: string): Promise<Record<string, unknown>[]> {
  return new Promise((resolve, reject) => {
    const child = spawn('td-cli', ['ai', 'get-context']);
    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (data) => { stdout += data; });
    child.stderr.on('data', (data) => { stderr += data; });

    child.on('close', (code) => {
      if (code === 0) {
        try {
          resolve(JSON.parse(stdout));
        } catch (e) {
          reject(new Error(`Failed to parse AI context: ${e instanceof Error ? e.message : String(e)}`));
        }
      } else {
        reject(new Error(`AI context error (code ${code}): ${stderr}`));
      }
    });

    child.on('error', (err) => {
      reject(err);
    });

    child.stdin.write(inputData);
    child.stdin.end();
  });
}

export async function getCodeDiffSummary(targetFiles?: string[]): Promise<CodeReviewSummary> {
  try {
    const { diffArgs, nameOnlyArgs, contextBaseRef } = await getGitArgs();

    let rawDiff: string;
    if (targetFiles && targetFiles.length > 0) {
      const specificDiffArgs = [...diffArgs, '--', ...targetFiles];
      const res = await execFile('git', specificDiffArgs, { encoding: 'utf-8', maxBuffer: 1024 * 1024 * 10 });
      rawDiff = (res.stdout as string) || '';
    } else {
      const res = await execFile('git', diffArgs, { encoding: 'utf-8', maxBuffer: 1024 * 1024 * 10 });
      rawDiff = (res.stdout as string) || '';
    }

    // basic sanity check - just take the first N chars if it's absurdly large to avoid blowing up context
    let diffContext = rawDiff;
    let isTruncated = false;
    let diffStat: string | undefined = undefined;

    if (rawDiff.length > MAX_DIFF_CHARS) {
      isTruncated = true;
      // Build robust stat arguments by replacing the diff mode with --stat
      const statArgs = ['diff', '--stat', ...diffArgs.slice(1).filter(arg => arg !== '-U10')];

      const specificStatArgs = (targetFiles && targetFiles.length > 0)
        ? [...statArgs, '--', ...targetFiles]
        : statArgs;

      try {
        const statRes = await execFile('git', specificStatArgs, {
          encoding: 'utf-8',
          maxBuffer: 1024 * 1024 * 10 // Use 10MB buffer for safety on large PRs
        });
        diffStat = (statRes.stdout as string) || '';
      } catch (err) {
        console.warn('⚠️  Failed to fetch git diff --stat for large PR:', err);
        diffStat = '[Error fetching diff stat summary]';
      }

      diffContext = rawDiff.slice(0, MAX_DIFF_CHARS) +
        `\n\n...[TRUNCATED FOR LLM]\n\nDIFF STAT SUMMARY:\n${diffStat}\n\n[The diff was truncated at ${MAX_DIFF_CHARS} characters. AI analysis may be incomplete.]`;
    }

    const fullDiff = rawDiff;
    const prGoal = await fetchPRGoal();
    let files: string[];
    if (targetFiles) {
      files = targetFiles;
    } else {
      const res = await execFile('git', nameOnlyArgs, { encoding: 'utf-8' });
      files = (res.stdout as string || '').split('\n').filter(Boolean);
    }


    // Context gathering
    const externalFilePaths = new Set<string>();
    let localDefinitions = '';

    for (const file of files) {
      if (!fs.existsSync(file)) continue;

      try {
        const diffResult = await execFile('git', ['diff', contextBaseRef, '--', file], { encoding: 'utf-8' });
        const fileDiff = diffResult.stdout || '';
        const fileContent = await fs.promises.readFile(file, 'utf-8');
        const imports = parseImports(fileContent);

        // Identify which imported symbols are used in the diff
        const symbolsUsedInDiff = new Set<string>();
        const wordRegex = /[a-zA-Z0-9_$]+/g;
        let wordMatch;
        while ((wordMatch = wordRegex.exec(fileDiff)) !== null) {
          symbolsUsedInDiff.add(wordMatch[0]);
        }

        for (const [symbol, importPath] of imports.entries()) {
          if (symbolsUsedInDiff.has(symbol)) {
            const resolved = resolveImportPath(importPath, file);
            if (resolved && resolved !== file) externalFilePaths.add(resolved);
          }
        }

        // Also look for definitions of symbols used in diff that are NOT imports
        // (likely defined in the same file but outside the diff window)
        const fileLines = fileContent.split('\n');
        for (const symbol of symbolsUsedInDiff) {
          if (!imports.has(symbol)) {
            // Very basic heuristic: look for "const symbol", "function symbol", "class symbol", "interface symbol", "type symbol"
            const defRegex = new RegExp(`(?:export\\s+)?(?:const|let|var|function|class|interface|type)\\s+${escapeRegExp(symbol)}\\b`);
            const defLineIndex = fileLines.findIndex(line => defRegex.test(line));
            if (defLineIndex !== -1) {
              // Only include if it's NOT already in the diff (diff-U10 usually covers 10 lines)
              // We'll just include a small window of the definition to external context
              const start = Math.max(0, defLineIndex - 2);
              const end = Math.min(fileLines.length, defLineIndex + 15);
              const defSnippet = fileLines.slice(start, end).join('\n');

              // We append this to externalContext later, for now we can just store it
              // Or better, we can treat the same file as an "external" file if we want to reuse the mechanism
              // but since externalFilePaths works with paths, let's just use a special handling or a pseudo-path
              // For simplicity, let's just append it to a dedicated string for now
              localDefinitions += `\n\n--- LOCAL DEF: ${file}:${defLineIndex + 1} (${symbol}) ---\n${defSnippet}`;
            }
          }
        }
      } catch (err) {
        console.warn(`Could not gather context for ${file}:`, err);
      }
    }

    let externalContext = localDefinitions;
    const maxExternalChars = 30000;
    for (const extPath of externalFilePaths) {
      if (externalContext.length >= maxExternalChars) break;
      if (fs.existsSync(extPath)) {
        const content = await fs.promises.readFile(extPath, 'utf-8');
        externalContext += `\n\n--- FILE: ${extPath} ---\n${content}`;
      }
    }

    if (externalContext.length > maxExternalChars) {
      externalContext = externalContext.slice(0, maxExternalChars) + '\n\n...[TRUNCATED EXTERNAL CONTEXT]';
    }

    const hasRealContent = externalContext.replace(/\n\n\.\.\.\[TRUNCATED EXTERNAL CONTEXT\]/g, '').trim().length > 0;

    // AI Context enrichment
    let impactSemanticContext = '';
    try {
      const batchFiles = [];
      for (const file of files) {
        if (!fs.existsSync(file)) continue;
        try {
          const diffResult = await execFile('git', ['diff', contextBaseRef, '--', file], { encoding: 'utf-8' });
          const fileDiff = (diffResult.stdout as string) || '';
          if (fileDiff) {
            batchFiles.push({ path: file, diff: fileDiff });
          }
        } catch (err) {
          console.warn(`Could not gather diff context for ${file}:`, err);
        }
      }

      if (batchFiles.length > 0) {
        const inputData = JSON.stringify({ files: batchFiles });
        const contextResults = await getAIContext(inputData);

        if (contextResults) {
          for (const ctx of contextResults) {
            if (ctx.dependencies?.length || ctx.dependents?.length || ctx.semantic?.length) {
              impactSemanticContext += `\n\n### Context for ${ctx.path}\n`;
              if (ctx.dependencies?.length) impactSemanticContext += `- Dependencies: ${ctx.dependencies.join(', ')}\n`;
              if (ctx.dependents?.length) impactSemanticContext += `- Impacted (dependents): ${ctx.dependents.join(', ')}\n`;
              if (ctx.semantic?.length) {
                impactSemanticContext += `- Semantically related snippets:\n`;
                for (const s of ctx.semantic) {
                  impactSemanticContext += `  - From ${s.path}:\n    \`\`\`\n    ${s.document.slice(0, 300).replace(/\n/g, '\n    ')}\n    \`\`\`\n`;
                }
              }
            }
          }
        }
      }
    } catch (err) {
      console.warn('Could not gather impact/semantic context:', err);
    }

    const summary: CodeReviewSummary = {
      diffContext,
      fullDiff,
      prGoal,
      changedFiles: files,
      externalContext: hasRealContent ? externalContext.trim() : undefined,
      impactSemanticContext: impactSemanticContext.trim() || undefined,
      isTruncated,
      diffStat,
    };

    summary.estimatedInputTokens = calculateEstimatedTokens([
      summary.diffContext,
      summary.externalContext || ''
    ]);

    return summary;
  } catch (error) {
    console.warn('Could not generate code diff:', error);
    return { diffContext: '' };
  }
}

export function generateTruncatedReviewMarkdown(
  summary: CodeReviewSummary,
  client: CodeReviewClientStrategy
): string {
  console.warn(`⚠️  Diff is too large (${summary.fullDiff?.length} chars) — skipping AI review and requesting human review.`);
  const prNumber = process.env.PR_NUMBER;
  const prLink = prNumber ? `[PR #${prNumber}](https://github.com/${process.env.GITHUB_REPOSITORY}/pull/${prNumber})` : 'this PR';

  const statSummary = summary.diffStat ? `\n\nDIFF STAT SUMMARY:\n${summary.diffStat}` : '';

  return `## ${client.reportTitle}

> ${client.botTagline}

**Reviewing:** ${prLink}

### ⚠️ Review Skipped: Large Diff Detected
The diff for this PR exceeds the maximum character limit for automated AI review. To ensure accuracy and prevent incomplete analysis, the AI review has been skipped for this round.

**Please perform a manual human review of these changes.**
${statSummary}

---
*Generated by ${client.botName}*
`;
}

export function generateCodeReviewMarkdown(
  result: CodeReviewResult,
  client: CodeReviewClientStrategy
): string {
  const prNumber = process.env.PR_NUMBER;
  const prLink = prNumber ? `[PR #${prNumber}](https://github.com/${process.env.GITHUB_REPOSITORY}/pull/${prNumber})` : 'this PR';

  // AFTER
  let costLine = '';
  if (result.cost > 0) {
    costLine = `**Cost:** ~$${result.cost.toFixed(5)} (${result.tokens} tokens)\n`;
  }
  const modelLine = result.modelName ? `**Model:** ${result.modelName}\n` : '';

  const displayFeedback = cleanupFeedback(result.feedback);

  return `## ${client.reportTitle}

> ${client.botTagline}

**Reviewing:** ${prLink}
${costLine}
${modelLine}

### Code Review Feedback
${displayFeedback}

---
*Generated by ${client.botName}*
`;
}

export async function orchestrateCodeReview(
  client: CodeReviewClientStrategy,
  allReportTitles: string[] = []
): Promise<void> {
  if (!fs.existsSync(ARTIFACTS_DIR)) {
    fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
  }

  const agentReportPath = path.join(ARTIFACTS_DIR, client.reportFileName);

  // Guarantee artifacts directory exists before any check or early return
  if (!fs.existsSync(ARTIFACTS_DIR)) {
    fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
  }

  const existing = await countExistingReviews(allReportTitles);
  if (existing >= MAX_REVIEWS_PER_PR) {
    console.log(`⏭️  Skipping ${client.botName} — ${existing}/${MAX_REVIEWS_PER_PR} reviews already posted.`);
    fs.writeFileSync(
      agentReportPath,
      `## ${client.reportTitle}\n\nSkipped: review quota (${MAX_REVIEWS_PER_PR}) already met.\n`
    );
    const prevState = await getPreviousReviewState<CodeReviewState>(client.reportTitle);
    fs.writeFileSync(path.join(ARTIFACTS_DIR, `${client.reportFileName.replace('.md', '')}-verdict.json`), JSON.stringify({
      passed: true,
      highCount: 0,
      routes: [],
      llmVerdict: 'pass',
      state: prevState
    }, null, 2));
    return;
  }

  // Get initial summary to find changed files
  const initialSummary = await getCodeDiffSummary();
  if (!initialSummary.diffContext) {
    console.log(`✅ No code changes detected — skipping agent review.`);
    fs.writeFileSync(agentReportPath, `## ${client.reportTitle}\n\nNo code changes detected.\n`);
    fs.writeFileSync(path.join(ARTIFACTS_DIR, `${client.reportFileName.replace('.md', '')}-verdict.json`), JSON.stringify({ passed: true, highCount: 0, routes: [], llmVerdict: 'pass' }, null, 2));
    return;
  }

  const prevState = await getPreviousReviewState<CodeReviewState>(client.reportTitle);
  const rawChangedFiles = Array.isArray(initialSummary.changedFiles) ? initialSummary.changedFiles : [];

  const changedFiles = filterLowImpactFiles(rawChangedFiles, IMPACT_CONFIG.LOW_IMPACT_PATHS);

  if (changedFiles.length === 0) {
    console.log(`✅ No reviewable code changes detected after filtering (${rawChangedFiles.length} files filtered) — skipping agent review.`);
    fs.writeFileSync(agentReportPath, `## ${client.reportTitle}\n\nNo reviewable code changes detected.\n`);
    fs.writeFileSync(path.join(ARTIFACTS_DIR, `${client.reportFileName.replace('.md', '')}-verdict.json`), JSON.stringify({
      passed: true,
      highCount: 0,
      routes: [],
      llmVerdict: 'pass',
      state: prevState
    }, null, 2));
    return;
  }

  if (initialSummary.isTruncated) {
    const report = generateTruncatedReviewMarkdown(initialSummary, client);
    fs.writeFileSync(agentReportPath, report);
    await postPRComment(report, client.reportTitle, prevState);

    const verdictPath = path.join(ARTIFACTS_DIR, `${client.reportFileName.replace('.md', '')}-verdict.json`);
    fs.writeFileSync(verdictPath, JSON.stringify({
      passed: true,
      highCount: 0,
      routes: [],
      llmVerdict: 'warn',
      isTruncated: true,
      state: prevState
    }, null, 2));
    return;
  }

  // Batch files (max 10 per batch)
  const fileBatches = batchFiles(changedFiles.sort(), 10);
  const roles: CodeReviewRole[] = ['SECURITY', 'PERFORMANCE', 'STYLE', 'ARCHITECTURE'];

  console.log(`🤖 Reviewing ${changedFiles.length} files in ${fileBatches.length} batches with ${roles.length} specialized agents...`);

  const orchestratorStartTime = Date.now();
  const allResults: CodeReviewResult[] = [];
  const CONCURRENCY_LIMIT = 4;
  const newCache: Record<string, CodeReviewResult> = {};

  const batchSummaryCache = new Map<string, Promise<CodeReviewSummary>>();
  const getMemoizedBatchSummary = async (batch: string[]) => {
    const key = batch.join(',');
    const cached = batchSummaryCache.get(key);
    if (cached) return cached;

    const promise = getCodeDiffSummary(batch);
    batchSummaryCache.set(key, promise);
    return promise;
  };

  const taskQueue: (() => Promise<void>)[] = [];

  for (const batch of fileBatches) {
    for (const role of roles) {
      taskQueue.push(async () => {
        try {
          const batchSummary = await getMemoizedBatchSummary(batch);
          if (!batchSummary.diffContext) {
            console.warn(`⚠️  Empty diff for batch ${batch.join(', ')} — skipping ${role} review.`);
            return;
          }

          const summary = { ...batchSummary, role, previousState: prevState };
          const hash = calculateReviewHash(summary);

          // Semantic Cache Check
          if (prevState?.cache?.[hash]) {
            console.log(`✨ Cache hit for ${role} (hash: ${hash.slice(0, 8)}) on batch ${batch.join(', ')} — skipping API call.`);
            const cachedResult = prevState.cache[hash];
            allResults.push(cachedResult);
            newCache[hash] = cachedResult;
            return;
          }

          const invokeWithTelemetry = async (forceMaxTokens?: number): Promise<CodeReviewResult> => {
            const start = Date.now();
            const result = await client.invokeReview(summary, forceMaxTokens);
            const durationMs = Date.now() - start;
            logReviewExecution('code-review', result, durationMs, {
              inputChars: getInputComplexity(summary)
            });
            return result;
          };

          let result = await invokeWithTelemetry();

          if (result.truncated) {
            console.warn(`⚠️  Initial review truncated — retrying once with a larger output budget.`);
            result = await invokeWithTelemetry(8192);
          }

          // HARD GATE: a truncated/malformed response must never silently resolve to PASS.
          // A cut-off <findings> block, or a verdict tag that got chopped off the end,
          // both currently degrade to the parser's default ('pass', undefined state) —
          // which would let real bugs slip through with zero signal anyone is missing.
          if (result.truncated || result.parseError) {
            const reason = result.truncated 
              ? "was truncated before completion (likely an output token limit)"
              : `had a malformed findings block (parse error: ${result.parseError})`;
            console.error(
              `❌ ${client.botName} output ${reason} — treating as inconclusive, not PASS.`
            );
            result = {
              ...result,
              llmVerdict: 'warn',
              feedback: `${result.feedback}\n\n---\n⚠️ **Review incomplete:** the model's response ${reason}. This review could not verify all findings and should not be treated as a clean pass. Consider re-running.`,
            };
          }

          // Final verification/reconciliation
          result = reconcileVerdict(result, summary.fullDiff || summary.diffContext);
          allResults.push(result);
          newCache[hash] = result;
        } catch (err) {
          const errorMsg = err instanceof Error ? err.message : String(err);
          console.error(`❌ Error in ${role} review task:`, err);
          allResults.push({
            feedback: `Error: failed to execute ${role} review. Details: ${errorMsg}`,
            role,
            tokens: 0,
            cost: 0,
            llmVerdict: 'warn',
          });
        }
      });
    }
  }

  // Execute with concurrency limit
  const workers = Array.from({ length: Math.min(CONCURRENCY_LIMIT, taskQueue.length) }, async () => {
    while (taskQueue.length > 0) {
      const task = taskQueue.shift();
      if (task) await task();
    }
  });

  await Promise.all(workers);
  const orchestratorDurationMs = Date.now() - orchestratorStartTime;

  // Clear batch summary cache to free memory
  batchSummaryCache.clear();

  // Aggregation logic - Sort results for deterministic output
  allResults.sort((a, b) => (a.role || '').localeCompare(b.role || ''));

  let aggregatedFeedback = '';
  const aggregatedFindings = [];
  let totalTokens = 0;
  let totalInputTokens = 0;
  let totalOutputTokens = 0;
  let totalCacheTokens = 0;
  let totalCost = 0;
  let finalVerdict: 'pass' | 'fail' | 'warn' = 'pass';
  const modelNames = new Set<string>();

  for (const res of allResults) {
    if (res.feedback) {
      if (res.feedback.startsWith('Error: failed to execute')) {
        console.warn(`⚠️  Skipping failed review output for ${res.role}`);
      } else {
        aggregatedFeedback += `\n\n#### [${res.role}] Review\n${res.feedback}`;
      }
    }
    if (res.state?.findings) {
      aggregatedFindings.push(...res.state.findings);
    }
    totalTokens += res.tokens;
    totalInputTokens += res.inputTokens ?? 0;
    totalOutputTokens += res.outputTokens ?? 0;
    totalCacheTokens += res.cacheTokens ?? 0;
    totalCost += res.cost;

    if (res.llmVerdict === 'fail') finalVerdict = 'fail';
    else if (res.llmVerdict === 'warn' && finalVerdict !== 'fail') finalVerdict = 'warn';

    if (res.modelName) modelNames.add(res.modelName);
  }

  // Restore findings omitted by LLM if we have previous state
  if (prevState?.findings) {
    const currentIds = new Set(aggregatedFindings.map(f => f.id));
    const missingFindings = prevState.findings.filter(f => !currentIds.has(f.id));

    if (missingFindings.length > 0) {
      const diffToVerify = initialSummary.fullDiff || initialSummary.diffContext;
      const restored = [];

      for (const finding of missingFindings) {
        if (finding.status === 'open' && finding.snippet) {
          if (!diffToVerify.includes(finding.snippet)) {
            finding.status = 'resolved';
            finding.fixSummary = 'Jules response: snippet no longer present in diff.';
            console.log(`✅ Auto-resolved finding: ${finding.issue}`);
          }
        }
        restored.push(finding);
      }

      if (restored.length > 0) {
        console.log(`♻️  Restoring ${restored.length} findings omitted by LLM agents.`);
        aggregatedFindings.push(...restored);
      }
    }
  }

  const finalResult: CodeReviewResult = {
    feedback: aggregatedFeedback.trim(),
    tokens: totalTokens,
    inputTokens: totalInputTokens,
    outputTokens: totalOutputTokens,
    cacheTokens: totalCacheTokens,
    cost: totalCost,
    llmVerdict: finalVerdict,
    state: {
      findings: aggregatedFindings,
      cache: pruneCache({ ...prevState?.cache, ...newCache }),
    },
    modelName: Array.from(modelNames).join(', '),
    durationMs: orchestratorDurationMs,
  };

  const report = generateCodeReviewMarkdown(finalResult, client);

  // Write local report
  fs.writeFileSync(agentReportPath, report);
  console.log(`✅ Local report written to ${agentReportPath}`);

  // Post to GitHub PR
  await postPRComment(report, client.reportTitle, finalResult.state);

  // Also alert Jules if this PR is from a Jules session
  const julesSessionId = await getJulesSessionIdFromPR();
  if (julesSessionId) {
    const isFail = finalResult.llmVerdict === 'fail';
    const passFailMsg = isFail ? "FAIL ❌" : "PASS ✅";
    const julesMessage = `[${client.reportTitle}] posted an aggregated code review (${passFailMsg}). Please read the review comments on the PR, analyze the diff context provided, and fix any failed or warned areas.`;
    await sendJulesMessage(julesSessionId, julesMessage);
  }

  const isFail = finalResult.llmVerdict === 'fail';
  const verdictPath = path.join(ARTIFACTS_DIR, `${client.reportFileName.replace('.md', '')}-verdict.json`);
  fs.writeFileSync(verdictPath, JSON.stringify({
    passed: !isFail,
    highCount: isFail ? 1 : 0,
    routes: [],
    llmVerdict: finalResult.llmVerdict,
    state: finalResult.state
  }, null, 2));

  if (isFail) {
    console.error(`❌ Code review returned FAIL — failing CI.`);
    process.exit(1);
  }
}


/**
 * Simple verdict reconciliation: ensures that a FAIL verdict is backed by at least one
 * open finding.
 */
export function reconcileVerdict(
  result: CodeReviewResult,
  _diffForVerification: string
): CodeReviewResult {
  if (result.llmVerdict !== 'fail') {
    return result;
  }

  const openFindings = result.state?.findings?.filter(f => f.status === 'open') || [];
  if (openFindings.length === 0) {
    console.warn(`⚠️  Downgrading FAIL→WARN: no open findings found to justify the FAIL verdict.`);
    return { ...result, llmVerdict: 'warn' };
  }

  return result;
}