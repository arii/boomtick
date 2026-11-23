/**
 * Offline dry-run of the review verdict path.
 * Usage: tsx scripts/review-dry-run.ts <fixture.json> [--own-pr]
 *
 * Runs the real orchestrateCodeReview and finalizeVerdictGate against a canned review
 * client. No Gemini or GitHub call is possible: credentials are removed from the
 * environment and the review runs in a throwaway git repo.
 */
import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

export interface DryRunResult {
  exitCode: number;
  outputs: string;
  summary: string;
  verdictJson: Record<string, any> | undefined;
}

const startDir = process.cwd();
let workDir: string | undefined;

function createTempRepo(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'boomtick-dry-run-'));
  const git = (...args: string[]) =>
    execFileSync('git', ['-c', 'user.name=dry-run', '-c', 'user.email=dry-run@example.com', ...args], { cwd: dir, stdio: 'ignore' });
  git('init', '-q');
  fs.mkdirSync(path.join(dir, 'src'));
  fs.writeFileSync(path.join(dir, 'src', 'app.ts'), 'export const a = 1;\n');
  git('add', '.');
  git('commit', '-q', '-m', 'base');
  fs.writeFileSync(path.join(dir, 'src', 'app.ts'), 'export const a = 2;\nexport function run(q: string) { return q; }\n');
  git('add', '.');
  git('commit', '-q', '-m', 'change');
  return dir;
}

export async function runDryRun(fixturePath: string, options: { ownPr?: boolean } = {}): Promise<DryRunResult> {
  const fixture = JSON.parse(fs.readFileSync(path.resolve(startDir, fixturePath), 'utf8')) as { feedback: string };

  // Safety: nothing below may reach GitHub or Gemini.
  for (const key of ['GITHUB_TOKEN', 'GITHUB_REPOSITORY', 'PR_NUMBER', 'GEMINI_API_KEY', 'GITHUB_BASE_REF', 'BOOMTICK_PR_NUMBER']) {
    delete process.env[key];
  }

  if (!workDir) {
    workDir = createTempRepo();
    process.chdir(workDir); // ARTIFACTS_DIR is computed from cwd at import time
  }
  const verdictPath = path.join(workDir, 'artifacts', 'gemini-code-review-verdict.json');
  fs.rmSync(verdictPath, { force: true });

  const outputFile = path.join(workDir, 'github-output.txt');
  const summaryFile = path.join(workDir, 'step-summary.md');
  fs.writeFileSync(outputFile, '');
  fs.writeFileSync(summaryFile, '');

  const { orchestrateCodeReview } = await import('../lib/codeReviewOrchestrator');
  const { parseCodeReviewVerdict, parseCodeReviewStateDetailed } = await import('../lib/codeReviewUtils');
  const { finalizeVerdictGate } = await import('../lib/verdictGate');

  const client = {
    botName: 'gemini-code-review',
    reportTitle: '👁 Gemini Code Review Agent',
    botTagline: 'Dry run',
    reportFileName: 'gemini-code-review.md',
    invokeReview: async (summary: { role: string }) => {
      const parsedState = parseCodeReviewStateDetailed(fixture.feedback);
      return {
        feedback: fixture.feedback,
        role: summary.role,
        tokens: 0,
        cost: 0,
        modelName: 'dry-run',
        llmVerdict: parseCodeReviewVerdict(fixture.feedback),
        findings: parsedState.state?.findings ?? [],
        state: { findings: parsedState.state?.findings ?? [] },
        isTruncated: false,
        parseError: parsedState.parseError,
      };
    },
  };

  await orchestrateCodeReview(client as any, [client.reportTitle]);

  // --own-pr: with no GitHub credentials the review post is skipped either way. The gate reads only
  // the verdict file, so it behaves the same as when GitHub falls back from APPROVE/REQUEST_CHANGES to COMMENT.
  if (options.ownPr) console.log('(own-PR mode: review would be posted as COMMENT; gate result is unaffected)');

  const previousExitCode = process.exitCode;
  process.exitCode = undefined;
  finalizeVerdictGate({
    reportFileName: client.reportFileName,
    failOnVerdict: true,
    env: { GITHUB_OUTPUT: outputFile, GITHUB_STEP_SUMMARY: summaryFile },
  });
  const exitCode = Number(process.exitCode ?? 0);
  process.exitCode = previousExitCode;

  return {
    exitCode,
    outputs: fs.readFileSync(outputFile, 'utf8'),
    summary: fs.readFileSync(summaryFile, 'utf8'),
    verdictJson: fs.existsSync(verdictPath) ? JSON.parse(fs.readFileSync(verdictPath, 'utf8')) : undefined,
  };
}

async function main(): Promise<void> {
  const fixture = process.argv[2];
  if (!fixture) {
    console.error('Usage: tsx scripts/review-dry-run.ts <fixture.json> [--own-pr]');
    process.exitCode = 2;
    return;
  }
  const result = await runDryRun(fixture, { ownPr: process.argv.includes('--own-pr') });
  console.log('--- GITHUB_OUTPUT ---\n' + result.outputs);
  console.log('--- GITHUB_STEP_SUMMARY ---\n' + result.summary);
  console.log(`--- dry-run exit code: ${result.exitCode} ---`);
  process.exitCode = result.exitCode;
}

if (require.main === module) {
  main().catch(err => {
    console.error(err);
    process.exitCode = 1;
  });
}
