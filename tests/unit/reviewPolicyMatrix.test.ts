/**
 * Pins the approved AI-review policy (arii/boomtick#1403):
 *  (a) infra problems never block merges: the verdict is WARN and the step exits 0;
 *  (b) a FAIL verdict with open HIGH findings stays red until the findings are resolved, including on
 *      later runs that are skipped, truncated or at the review cap. Nothing flips it to pass on its own.
 *
 * Runs the real orchestrateCodeReview + finalizeVerdictGate against canned clients in a throwaway git
 * repo. GitHub state (review count, previous review state, PR comment) is stubbed. No network.
 */
import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const gh = vi.hoisted(() => ({
  existing: 0,
  prevState: undefined as unknown,
  posted: [] as Array<{ verdict?: string }>,
}));

vi.mock('../../lib/visualReviewUtils', async importOriginal => ({
  ...(await importOriginal<typeof import('../../lib/visualReviewUtils')>()),
  countExistingReviews: vi.fn(async () => gh.existing),
  getPreviousReviewState: vi.fn(async () => gh.prevState),
  postPRComment: vi.fn(async (_body: string, _title: string, _state: unknown, verdict?: string) => {
    gh.posted.push({ verdict });
  }),
}));

const MAX_REVIEWS = 10;

const open = (over: Record<string, unknown> = {}) => ({
  id: 'F1', file: 'src/app.ts', line: 3, issue: 'User input is concatenated into a SQL query',
  status: 'open', severity: 'HIGH', confidence: 'high', ...over,
});

const reviewText = (verdict: 'PASS' | 'WARN' | 'FAIL', findings: unknown[] = []) =>
  `[VERDICT: ${verdict}]\n\n<findings>\n${JSON.stringify({ findings })}\n</findings>`;

type Outcome = {
  exitCode: number;
  gateVerdict: string;
  fileVerdict: unknown;
  skipReason: unknown;
  message: string;
  summary: string;
  posted: Array<{ verdict?: string }>;
  state: { findings?: Array<Record<string, any>> } | undefined;
};

let workDir: string;
let startDir: string;
let orchestrate: typeof import('../../lib/codeReviewOrchestrator').orchestrateCodeReview;
let finalize: typeof import('../../lib/verdictGate').finalizeVerdictGate;
let geminiClient: typeof import('../../scripts/clients/geminiCodeReviewClient').geminiCodeReviewClient;
let baseSha: string;

const git = (...args: string[]) =>
  execFileSync('git', ['-c', 'user.name=matrix', '-c', 'user.email=matrix@example.com', ...args], { cwd: workDir, stdio: 'ignore' });

/** Reset to the base commit, then commit `files` on top as the PR change. */
function setChange(files: Record<string, string>) {
  git('reset', '-q', '--hard', baseSha);
  for (const [name, content] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(workDir, name)), { recursive: true });
    fs.writeFileSync(path.join(workDir, name), content);
  }
  git('add', '.');
  git('commit', '-q', '-m', 'change');
}

const REVIEWABLE = { 'src/app.ts': 'export const a = 2;\nexport function run(q: string) { return q; }\n' };
const LOW_IMPACT_ONLY = { 'pnpm-lock.yaml': 'lockfileVersion: 9\n' };
// MAX_DIFF_CHARS defaults to 250000 (lib/projectConfig.ts).
const HUGE = { 'src/big.ts': Array.from({ length: 3000 }, (_, i) => `// ${i} ${'x'.repeat(90)}`).join('\n') + '\n' };

type Client = Parameters<typeof orchestrate>[0];

const cannedClient = (invoke: (role: string) => unknown): Client => ({
  botName: 'gemini-code-review',
  reportTitle: '👁 Gemini Code Review Agent',
  botTagline: 'matrix',
  reportFileName: 'gemini-code-review.md',
  invokeReview: async (summary: { role: string }) => invoke(summary.role) as any,
});

async function parsed(text: string) {
  const { parseCodeReviewVerdict, parseCodeReviewStateDetailed } = await import('../../lib/codeReviewUtils');
  const st = parseCodeReviewStateDetailed(text);
  return {
    feedback: text, tokens: 0, cost: 0, modelName: 'canned',
    llmVerdict: parseCodeReviewVerdict(text),
    findings: st.state?.findings ?? [],
    state: { findings: st.state?.findings ?? [] },
    isTruncated: false,
    parseError: st.parseError,
  };
}

/** Same code path as the action: orchestrate, then the verdict gate with fail-on-verdict as given. */
async function run(client: Client, failOnVerdict = true): Promise<Outcome> {
  gh.posted = [];
  const verdictPath = path.join(workDir, 'artifacts', 'gemini-code-review-verdict.json');
  fs.rmSync(verdictPath, { force: true });
  const outputFile = path.join(workDir, 'github-output.txt');
  const summaryFile = path.join(workDir, 'step-summary.md');
  fs.writeFileSync(outputFile, '');
  fs.writeFileSync(summaryFile, '');

  await orchestrate(client, [client.reportTitle]);

  const previous = process.exitCode;
  process.exitCode = undefined;
  const gate = finalize({
    reportFileName: client.reportFileName,
    failOnVerdict,
    env: { GITHUB_OUTPUT: outputFile, GITHUB_STEP_SUMMARY: summaryFile },
  });
  const exitCode = Number(process.exitCode ?? 0);
  process.exitCode = previous;

  const file = JSON.parse(fs.readFileSync(verdictPath, 'utf8'));
  const outputs = fs.readFileSync(outputFile, 'utf8');
  return {
    exitCode,
    gateVerdict: /^verdict=(.*)$/m.exec(outputs)?.[1] ?? '',
    fileVerdict: file.llmVerdict,
    skipReason: file.skipReason,
    message: gate.message,
    summary: fs.readFileSync(summaryFile, 'utf8'),
    posted: gh.posted,
    state: file.state,
  };
}

beforeAll(async () => {
  startDir = process.cwd();
  for (const key of ['GITHUB_TOKEN', 'GITHUB_REPOSITORY', 'PR_NUMBER', 'GEMINI_API_KEY', 'GEMINI_MODEL', 'GITHUB_BASE_REF', 'BOOMTICK_PR_NUMBER']) {
    delete process.env[key];
  }
  workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'boomtick-policy-matrix-'));
  git('init', '-q');
  fs.mkdirSync(path.join(workDir, 'src'));
  fs.writeFileSync(path.join(workDir, 'src', 'app.ts'), 'export const a = 1;\n');
  git('add', '.');
  git('commit', '-q', '-m', 'base');
  baseSha = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: workDir }).toString().trim();
  process.chdir(workDir); // ARTIFACTS_DIR is computed from cwd at import time
  vi.resetModules();
  ({ orchestrateCodeReview: orchestrate } = await import('../../lib/codeReviewOrchestrator'));
  ({ finalizeVerdictGate: finalize } = await import('../../lib/verdictGate'));
  ({ geminiCodeReviewClient: geminiClient } = await import('../../scripts/clients/geminiCodeReviewClient'));
});

afterAll(() => {
  process.chdir(startDir);
  fs.rmSync(workDir, { recursive: true, force: true });
});

beforeEach(() => {
  gh.existing = 0;
  gh.prevState = undefined;
  delete process.env.GEMINI_API_KEY;
  delete process.env.GEMINI_MODEL;
  setChange(REVIEWABLE);
});

describe('review policy matrix (#1403)', () => {
  describe('verdicts from a completed review', () => {
    it('PASS verdict: written pass, gate pass, exit 0', async () => {
      const r = await run(cannedClient(() => parsed(reviewText('PASS'))));
      expect([r.fileVerdict, r.gateVerdict, r.exitCode]).toEqual(['pass', 'pass', 0]);
    });

    it('FAIL verdict with an open HIGH finding: exit 1 and the finding is listed', async () => {
      const r = await run(cannedClient(() => parsed(reviewText('FAIL', [open()]))));
      expect([r.fileVerdict, r.gateVerdict, r.exitCode]).toEqual(['fail', 'fail', 1]);
      expect(r.message).toContain('- [HIGH] src/app.ts:3 - User input is concatenated into a SQL query');
      expect(r.summary).toContain('AI review verdict: FAIL');
    });

    it('FAIL verdict with fail-on-verdict false: same verdict, exit 0', async () => {
      const r = await run(cannedClient(() => parsed(reviewText('FAIL', [open()]))), false);
      expect([r.fileVerdict, r.gateVerdict, r.exitCode]).toEqual(['fail', 'fail', 0]);
    });
  });

  describe('(a) infra problems warn and pass', () => {
    const infraRows: Array<{ name: string; skipReason: string; client: () => Client }> = [
      {
        name: 'GEMINI_API_KEY missing, model discovery finds nothing (UNHANDLED_ERROR: "No verified active catalog Gemini model")',
        skipReason: 'UNHANDLED_ERROR',
        client: () => geminiClient,
      },
      {
        name: 'GEMINI_API_KEY missing with GEMINI_MODEL pinned (UNHANDLED_ERROR: "Missing GEMINI_API_KEY environment variable")',
        skipReason: 'UNHANDLED_ERROR',
        client: () => {
          process.env.GEMINI_MODEL = 'gemini-matrix-test';
          return geminiClient;
        },
      },
      {
        name: 'API key rejected, 401/API_KEY_INVALID (MISSING_API_KEY)',
        skipReason: 'MISSING_API_KEY',
        client: () => cannedClient(() => { throw new Error('[401] API_KEY_INVALID: API key not valid'); }),
      },
      {
        name: 'Gemini unavailable / model selection unverified, #1341 (UNHANDLED_ERROR)',
        skipReason: 'UNHANDLED_ERROR',
        client: () => cannedClient(() => { throw new Error('No verified active catalog Gemini model can handle this input; model discovery, access or catalog refresh is required.'); }),
      },
      {
        name: 'Gemini outage, 503 (UNHANDLED_ERROR)',
        skipReason: 'UNHANDLED_ERROR',
        client: () => cannedClient(() => { throw new Error('503 Service Unavailable'); }),
      },
      {
        name: 'rate limit, 429 (RATE_LIMIT)',
        skipReason: 'RATE_LIMIT',
        client: () => cannedClient(() => { throw new Error('429 Too Many Requests: rate limit exceeded'); }),
      },
      {
        name: 'truncated model output (TRUNCATED)',
        skipReason: 'TRUNCATED',
        client: () => cannedClient(async role => ({ ...(await parsed(reviewText('PASS'))), role, isTruncated: true, llmVerdict: 'warn' })),
      },
      {
        name: 'malformed findings block (PARSE_ERROR)',
        skipReason: 'PARSE_ERROR',
        client: () => cannedClient(async role => ({
          ...(await parsed('[VERDICT: PASS]\n<findings>{not json</findings>')),
          role, findings: undefined, state: undefined,
        })),
      },
      {
        name: 'unhandled error inside a review task (UNHANDLED_ERROR)',
        skipReason: 'UNHANDLED_ERROR',
        client: () => cannedClient(() => { throw new Error('boom'); }),
      },
    ];

    for (const row of infraRows) {
      it(`${row.name}: warn, exit 0 with fail-on-verdict true and false`, async () => {
        const client = row.client();
        const strict = await run(client, true);
        expect([strict.fileVerdict, strict.gateVerdict, strict.exitCode]).toEqual(['warn', 'warn', 0]);
        expect(strict.skipReason).toContain(row.skipReason);
        expect(strict.message).toContain(row.skipReason);
        const lenient = await run(client, false);
        expect([lenient.fileVerdict, lenient.gateVerdict, lenient.exitCode]).toEqual(['warn', 'warn', 0]);
      });
    }

    it('truncated diff (isTruncated, no model call): warn, exit 0', async () => {
      setChange(HUGE);
      const invoke = vi.fn();
      const r = await run(cannedClient(invoke));
      expect(invoke).not.toHaveBeenCalled();
      expect([r.fileVerdict, r.gateVerdict, r.exitCode]).toEqual(['warn', 'warn', 0]);
    });

    it('own-PR COMMENT fallback never changes the exit code (see verdictGate.test.ts)', async () => {
      // The 422 own-PR fallback in postPRComment is covered in tests/unit/verdictGate.test.ts.
      // Here: a posting problem is not part of the verdict, so a PASS review stays exit 0.
      const r = await run(cannedClient(() => parsed(reviewText('PASS'))));
      expect(r.posted.length).toBeGreaterThan(0);
      expect(r.posted.every(p => p.verdict === 'pass')).toBe(true);
      expect(r.exitCode).toBe(0);
    });
  });

  describe('(b) a prior FAIL stays red', () => {
    const priorFail = () => ({ findings: [open()] });
    const expectRed = (r: Outcome) => {
      expect([r.fileVerdict, r.gateVerdict, r.exitCode]).toEqual(['fail', 'fail', 1]);
      expect(r.message).toContain('- [HIGH] src/app.ts:3 - User input is concatenated into a SQL query');
    };

    // KNOWN MISMATCH with decision (b), not fixed here (behavior change for Ari). `it.fails` passes while the
    // code is wrong and starts failing once it is fixed, which is the cue to switch these to plain `it`.
    // Observed: the verdict file is written as pass and the step exits 0. Expected: fail, exit 1.
    it.fails('MISMATCH: later run with no reviewable change (low-impact files only): still fail, exit 1, prior findings listed', async () => {
      setChange(LOW_IMPACT_ONLY);
      gh.prevState = priorFail();
      const invoke = vi.fn();
      expectRed(await run(cannedClient(invoke)));
      expect(invoke).not.toHaveBeenCalled();
    });

    it.fails('MISMATCH: later run with no code change at all: still fail, exit 1', async () => {
      // An empty diff takes the "No code changes detected" exit, which passes null as the previous state.
      git('reset', '-q', '--hard', baseSha);
      gh.prevState = priorFail();
      const r = await run(cannedClient(vi.fn()));
      expect(r.exitCode).toBe(1);
      expect(r.fileVerdict).toBe('fail');
    });

    it('later run at the review cap (MAX_AI_REVIEWS reached): still fail, exit 1, no model call', async () => {
      gh.existing = MAX_REVIEWS;
      gh.prevState = priorFail();
      const invoke = vi.fn();
      expectRed(await run(cannedClient(invoke)));
      expect(invoke).not.toHaveBeenCalled();
    });

    it('hitting the cap repeatedly stays red and never turns green', async () => {
      gh.prevState = priorFail();
      for (const existing of [MAX_REVIEWS, MAX_REVIEWS + 1, MAX_REVIEWS + 5]) {
        gh.existing = existing;
        expectRed(await run(cannedClient(vi.fn())));
        // The next run reads back the state this run wrote, as the PR comment would carry it.
        const written = JSON.parse(fs.readFileSync(path.join(workDir, 'artifacts', 'gemini-code-review-verdict.json'), 'utf8'));
        gh.prevState = written.state;
      }
    });

    it.fails('MISMATCH: later run with a truncated diff: still fail, exit 1, prior findings listed', async () => {
      setChange(HUGE);
      gh.prevState = priorFail();
      expectRed(await run(cannedClient(vi.fn())));
    });

    it.fails('MISMATCH: later run where every review task is rate limited: still fail, exit 1', async () => {
      gh.prevState = priorFail();
      expectRed(await run(cannedClient(() => { throw new Error('429 rate limit'); })));
    });

    it.fails('MISMATCH: later run where the model output is truncated: still fail, exit 1', async () => {
      gh.prevState = priorFail();
      expectRed(await run(cannedClient(async role => ({ ...(await parsed(reviewText('PASS'))), role, isTruncated: true, llmVerdict: 'warn' }))));
    });

    it('a later review that still reports the finding open stays fail', async () => {
      gh.prevState = priorFail();
      expectRed(await run(cannedClient(() => parsed(reviewText('FAIL', [open()])))));
    });

    it('only a later review with the prior findings closed in state yields pass', async () => {
      gh.prevState = priorFail();
      const r = await run(cannedClient(() => parsed(reviewText('PASS', [open({ status: 'resolved', fixSummary: 'Parameterized the query.' })]))));
      expect([r.fileVerdict, r.gateVerdict, r.exitCode]).toEqual(['pass', 'pass', 0]);
      expect(r.state?.findings?.every(f => f.status === 'resolved')).toBe(true);
    });

    it('once the state has no open HIGH findings, a capped run is pass (the state, not the cap, decides)', async () => {
      gh.existing = MAX_REVIEWS;
      gh.prevState = { findings: [open({ status: 'resolved' })] };
      const r = await run(cannedClient(vi.fn()));
      expect([r.fileVerdict, r.gateVerdict, r.exitCode]).toEqual(['pass', 'pass', 0]);
    });
  });
});
