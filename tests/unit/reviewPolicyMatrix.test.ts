/**
 * Pins the approved AI-review policy (arii/boomtick#1403):
 *  (a) infra problems warn and exit 0 when there is no prior FAIL;
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
  stateError: undefined as Error | undefined,
  posted: [] as Array<{ verdict?: string }>,
}));

vi.mock('../../lib/visualReviewUtils', async importOriginal => ({
  ...(await importOriginal<typeof import('../../lib/visualReviewUtils')>()),
  countExistingReviews: vi.fn(async () => gh.existing),
  getPreviousReviewState: vi.fn(async () => {
    if (gh.stateError) throw gh.stateError;
    return gh.prevState;
  }),
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
async function run(
  client: Client,
  failOnVerdict = true,
  execute = () => orchestrate(client, [client.reportTitle]),
): Promise<Outcome> {
  gh.posted = [];
  const verdictPath = path.join(workDir, 'artifacts', 'gemini-code-review-verdict.json');
  fs.rmSync(verdictPath, { force: true });
  const outputFile = path.join(workDir, 'github-output.txt');
  const summaryFile = path.join(workDir, 'step-summary.md');
  fs.writeFileSync(outputFile, '');
  fs.writeFileSync(summaryFile, '');

  await execute();

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
    }, 30000);

    it('own-PR COMMENT fallback never changes the exit code (see verdictGate.test.ts)', async () => {
      // The 422 own-PR fallback in postPRComment is covered in tests/unit/verdictGate.test.ts.
      // Here: a posting problem is not part of the verdict, so a PASS review stays exit 0.
      const r = await run(cannedClient(() => parsed(reviewText('PASS'))));
      expect(r.posted.length).toBeGreaterThan(0);
      expect(r.posted.every(p => p.verdict === 'pass')).toBe(true);
      expect(r.exitCode).toBe(0);
    });
  });

  it.each([false, true])('the missing-key runner skip preserves a prior FAIL when present (%s)', async hasPriorFail => {
    const { runReviewScript } = await import('../../scripts/utils/reviewScriptRunner');
    const { getPreviousReviewState } = await import('../../lib/visualReviewUtils');
    gh.prevState = hasPriorFail ? { findings: [open()] } : undefined;
    const orchestrateGemini = vi.fn(async () => undefined);
    const argv = process.argv;
    process.argv = [...argv.slice(0, 2), 'gemini'];
    try {
      const r = await run(geminiClient, true, () => runReviewScript({
        geminiClient,
        orchestrateGemini,
        scriptName: 'code review',
        getPreviousState: () => getPreviousReviewState(geminiClient.reportTitle),
      }));
      const verdict = hasPriorFail ? 'fail' : 'warn';
      expect([r.fileVerdict, r.gateVerdict, r.exitCode]).toEqual([verdict, verdict, hasPriorFail ? 1 : 0]);
      expect(r.skipReason).toBe('MISSING_API_KEY');
      if (hasPriorFail) expect(r.state?.findings).toEqual([open()]);
      expect(orchestrateGemini).not.toHaveBeenCalled();
    } finally {
      process.argv = argv;
    }
  });

  describe('(b) a prior FAIL stays red', () => {
    const priorFail = () => ({ findings: [open({ snippet: 'a prior snippet absent from the current diff' })] });
    const expectRed = (r: Outcome) => {
      expect([r.fileVerdict, r.gateVerdict, r.exitCode]).toEqual(['fail', 'fail', 1]);
      expect(r.message).toContain('- [HIGH] src/app.ts:3 - User input is concatenated into a SQL query');
    };

    it('later run with no reviewable change (low-impact files only): still fail, exit 1, prior findings listed', async () => {
      setChange(LOW_IMPACT_ONLY);
      gh.prevState = priorFail();
      const invoke = vi.fn();
      expectRed(await run(cannedClient(invoke)));
      expect(invoke).not.toHaveBeenCalled();
    });

    it('later run with no code change at all: still fail, exit 1', async () => {
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

    it('later run with a truncated diff: still fail, exit 1, prior findings listed', async () => {
      setChange(HUGE);
      gh.prevState = priorFail();
      const invoke = vi.fn();
      const r = await run(cannedClient(invoke));
      expectRed(r);
      expect(r.posted).toEqual([{ verdict: 'fail' }]);
      expect(invoke).not.toHaveBeenCalled();
    }, 30000);

    it('later run where every review task is rate limited: still fail, exit 1', async () => {
      gh.prevState = priorFail();
      expectRed(await run(cannedClient(() => { throw new Error('429 rate limit'); })));
    });

    it('later run where the model output is truncated: still fail, exit 1', async () => {
      gh.prevState = priorFail();
      expectRed(await run(cannedClient(async role => ({ ...(await parsed(reviewText('PASS'))), role, isTruncated: true, llmVerdict: 'warn' }))));
    });

    it('later run with malformed findings and an empty findings array: still fail, exit 1', async () => {
      gh.prevState = priorFail();
      expectRed(await run(cannedClient(() => parsed('[VERDICT: PASS]\n<findings>{not json</findings>'))));
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

    it('a resolution from a completed task survives another task failing in the same run', async () => {
      gh.prevState = priorFail();
      let calls = 0;
      const r = await run(cannedClient(async () => {
        calls += 1;
        if (calls === 1) throw new Error('429 rate limit');
        return parsed(reviewText('PASS', [open({ status: 'resolved', fixSummary: 'Parameterized the query.' })]));
      }));
      expect(r.state?.findings?.every(f => f.status === 'resolved')).toBe(true);
      expect(r.fileVerdict).not.toBe('fail');
      expect(r.exitCode).toBe(0);
    });

    it('an incomplete result is not cached, so the next run with the same diff calls the model again', async () => {
      gh.prevState = priorFail();
      const truncated = async () => ({ ...(await parsed(reviewText('PASS'))), isTruncated: true, llmVerdict: 'warn' });
      const first = await run(cannedClient(truncated));
      expectRed(first);
      expect(Object.keys(first.state?.cache ?? {})).toHaveLength(0);
      gh.prevState = first.state;
      const invoke = vi.fn(() => parsed(reviewText('PASS', [open({ status: 'resolved', fixSummary: 'Parameterized the query.' })])));
      const second = await run(cannedClient(invoke));
      expect(invoke).toHaveBeenCalled();
      expect([second.fileVerdict, second.exitCode]).toEqual(['pass', 0]);
    });

    it('an incomplete run does not auto-resolve a prior finding whose snippet left the diff', async () => {
      gh.prevState = priorFail();
      const r = await run(cannedClient(() => { throw new Error('429 rate limit'); }));
      expectRed(r);
      expect(r.state?.findings?.some(f => f.status === 'open')).toBe(true);
    });

    it('a previous-state fetch error on the no-change path warns instead of throwing', async () => {
      git('reset', '-q', '--hard', baseSha);
      gh.stateError = new Error('GitHub API 502');
      try {
        const r = await run(cannedClient(vi.fn()));
        expect(r.exitCode).toBe(0);
      } finally {
        gh.stateError = undefined;
      }
    });

    it('once the state has no open HIGH findings, a capped run is pass (the state, not the cap, decides)', async () => {
      gh.existing = MAX_REVIEWS;
      gh.prevState = { findings: [open({ status: 'resolved' })] };
      const r = await run(cannedClient(vi.fn()));
      expect([r.fileVerdict, r.gateVerdict, r.exitCode]).toEqual(['pass', 'pass', 0]);
    });
  });
});
