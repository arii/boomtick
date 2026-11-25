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
  isTruncated?: boolean;
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

/** Model output is untrusted: collapse newlines and control characters so one finding stays on one line. */
function sanitizeText(value: unknown): string {
  // eslint-disable-next-line no-control-regex
  return String(value ?? '').replace(/[\u0000-\u001f\u007f-\u009f\u2028\u2029]+/g, ' ').trim();
}

function escapeMarkdown(value: string): string {
  return value.replace(/[\\`*_<>[\]|]/g, c => `\\${c}`);
}

function formatFinding(f: BlockingFinding): string {
  const file = sanitizeText(f.file);
  const location = f.line ? `${file}:${Number(f.line) || ''}` : file;
  const text = sanitizeText(f.issue);
  const issue = text.length > MAX_ISSUE_LENGTH ? `${text.slice(0, MAX_ISSUE_LENGTH)}...` : text;
  return `- [${sanitizeText(f.severity)}] ${location} - ${issue}`;
}

export function evaluateVerdictGate(
  data: VerdictFileData | undefined,
  options: { failOnVerdict: boolean }
): VerdictGateResult {
  const raw = data?.llmVerdict;
  const verdict: GateVerdict = raw === 'pass' || raw === 'warn' || raw === 'fail' ? raw : 'unknown';
  // Execution failure is not a review verdict or a policy gate. Never report it as success.
  const executionReasons = new Set([
    'RATE_LIMIT', 'MISSING_API_KEY', 'UNHANDLED_ERROR', 'PARSE_ERROR', 'TRUNCATED', 'NO_REVIEW_RESULTS', 'EMPTY_REVIEW',
  ]);
  const executionFailed = verdict === 'unknown' || data?.isTruncated === true || (data?.skipReason ?? '')
    .split(',').some(reason => executionReasons.has(reason.trim()));
  const shouldFail = executionFailed || (options.failOnVerdict && verdict === 'fail');

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
  if (executionFailed) {
    const reason = data?.skipReason || (data?.isTruncated ? 'TRUNCATED' : 'MISSING_OR_INVALID_VERDICT');
    message = `AI review execution failed: ${sanitizeText(reason)}. No completed review is established.`;
    if (blockingFindings.length) message += `\n${blockingFindings.slice(0, MAX_LISTED).map(formatFinding).join('\n')}`;
  } else if (verdict === 'fail' && blockingFindings.length === 0) {
    message = 'AI review verdict: FAIL. The review returned FAIL without parseable findings.';
  } else if (verdict === 'fail') {
    const lines = blockingFindings.slice(0, MAX_LISTED).map(formatFinding);
    if (blockingFindings.length > MAX_LISTED) {
      lines.push(`...and ${blockingFindings.length - MAX_LISTED} more`);
    }
    message = `AI review verdict: FAIL. ${blockingFindings.length} blocking finding(s):\n${lines.join('\n')}`;
  } else {
    message = `AI review verdict: ${verdict.toUpperCase()}.`;
    if (verdict === 'warn' && data?.skipReason) message += ` Reason: ${sanitizeText(data.skipReason)}`;
  }

  let note = '';
  if (executionFailed) note = '\nThis check fails because review execution did not complete, independent of fail-on-verdict.\n';
  else if (shouldFail) note = '\nThis check fails because fail-on-verdict is enabled.\n';
  else if (verdict === 'warn') {
    note = '\nA completed WARN verdict does not fail this check. Execution failures are reported separately.\n';
  }
  const summaryMarkdown = `### AI review verdict: ${verdict.toUpperCase()}\n\n${escapeMarkdown(message)}\n${note}`;

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
    console.log(`::error title=AI review failure::${escapeAnnotation(result.message)}`);
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
