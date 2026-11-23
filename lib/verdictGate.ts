import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import { ARTIFACTS_DIR } from './visualReviewConstants';

export type GateVerdict = 'pass' | 'warn' | 'fail' | 'unknown';

export interface BlockingFinding {
  severity: string;
  file: string;
  line?: number;
  issue: string;
}

export interface VerdictFileData {
  llmVerdict?: string;
  skipReason?: string;
  state?: {
    findings?: Array<{
      status?: string;
      severity?: string;
      file?: string;
      line?: number;
      issue?: string;
    }>;
  };
}

export interface VerdictGateResult {
  verdict: GateVerdict;
  shouldFail: boolean;
  blockingFindings: BlockingFinding[];
  message: string;
  summaryMarkdown: string;
}

const MAX_LISTED = 10;
const MAX_ISSUE_LENGTH = 200;

export function readVerdictFile(filePath: string): VerdictFileData | undefined {
  try {
    const parsed = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    return parsed && typeof parsed === 'object' ? (parsed as VerdictFileData) : undefined;
  } catch {
    return undefined;
  }
}

function isHigh(severity?: string): boolean {
  return severity === 'HIGH' || severity === 'error';
}

function formatFinding(f: BlockingFinding): string {
  const location = f.line ? `${f.file}:${f.line}` : f.file;
  const issue = f.issue.length > MAX_ISSUE_LENGTH ? `${f.issue.slice(0, MAX_ISSUE_LENGTH)}...` : f.issue;
  return `- [${f.severity}] ${location} - ${issue}`;
}

export function evaluateVerdictGate(
  data: VerdictFileData | undefined,
  options: { failOnVerdict: boolean }
): VerdictGateResult {
  const raw = data?.llmVerdict;
  const verdict: GateVerdict = raw === 'pass' || raw === 'warn' || raw === 'fail' ? raw : 'unknown';
  const shouldFail = options.failOnVerdict && verdict === 'fail';

  let blockingFindings: BlockingFinding[] = [];
  if (verdict === 'fail') {
    const open = (data?.state?.findings ?? []).filter(f => f.status === 'open');
    const high = open.filter(f => isHigh(f.severity));
    const seen = new Set<string>();
    // Several review roles can report the same finding, so list each file:line/issue once.
    for (const f of high.length > 0 ? high : open) {
      const finding = {
        severity: f.severity ?? 'UNSPECIFIED',
        file: f.file ?? '(unknown file)',
        line: f.line,
        issue: f.issue ?? '(no description)',
      };
      const key = `${finding.file}:${finding.line ?? ''}:${finding.issue}`;
      if (seen.has(key)) continue;
      seen.add(key);
      blockingFindings.push(finding);
    }
  }

  let message: string;
  if (verdict === 'fail' && blockingFindings.length === 0) {
    message = 'AI review verdict: FAIL. The review returned FAIL without parseable findings.';
  } else if (verdict === 'fail') {
    const lines = blockingFindings.slice(0, MAX_LISTED).map(formatFinding);
    if (blockingFindings.length > MAX_LISTED) {
      lines.push(`...and ${blockingFindings.length - MAX_LISTED} more`);
    }
    message = `AI review verdict: FAIL. ${blockingFindings.length} blocking finding(s):\n${lines.join('\n')}`;
  } else {
    message = `AI review verdict: ${verdict.toUpperCase()}.`;
    if (verdict === 'warn' && data?.skipReason) message += ` Reason: ${data.skipReason}`;
  }

  const summaryMarkdown = `### AI review verdict: ${verdict.toUpperCase()}\n\n${message}\n${
    shouldFail ? '\nThis check fails because fail-on-verdict is enabled.\n' : ''
  }`;

  return { verdict, shouldFail, blockingFindings, message, summaryMarkdown };
}

function escapeAnnotation(value: string): string {
  return value.replace(/%/g, '%25').replace(/\r/g, '%0D').replace(/\n/g, '%0A');
}

export function publishVerdictGate(
  result: VerdictGateResult,
  env: NodeJS.ProcessEnv = process.env
): void {
  if (env.GITHUB_OUTPUT) {
    const delimiter = `EOF_${crypto.randomBytes(8).toString('hex')}`;
    fs.appendFileSync(
      env.GITHUB_OUTPUT,
      `verdict=${result.verdict}\nblocking-findings<<${delimiter}\n${result.message}\n${delimiter}\n`
    );
  }
  if (env.GITHUB_STEP_SUMMARY) {
    fs.appendFileSync(env.GITHUB_STEP_SUMMARY, `${result.summaryMarkdown}\n`);
  }
  if (result.shouldFail) {
    console.log(`::error title=AI review verdict: FAIL::${escapeAnnotation(result.message)}`);
    console.error(result.message);
    process.exitCode = 1;
  }
}

export function finalizeVerdictGate(options: {
  reportFileName: string;
  failOnVerdict: boolean;
  env?: NodeJS.ProcessEnv;
}): VerdictGateResult {
  const verdictPath = path.join(
    ARTIFACTS_DIR,
    `${path.basename(options.reportFileName).replace('.md', '')}-verdict.json`
  );
  const result = evaluateVerdictGate(readVerdictFile(verdictPath), { failOnVerdict: options.failOnVerdict });
  publishVerdictGate(result, options.env);
  return result;
}
