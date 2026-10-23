import * as path from 'path';
import * as crypto from 'crypto';
import type { CodeReviewSummary, CodeReviewState, ParsedFindingsResult, CodeReviewResult, ReviewFinding, CodeReviewParseError } from './codeReviewTypes';

/**
 * Generates a stable SHA-256 hash for a code review batch.
 * Includes diff context, role, goal, and all relevant semantic/external context.
 * Explicitly handles undefined values to ensure stable serialization.
 */
const DEFAULT_EXCLUDED_PATTERNS = [
  'pnpm-lock.yaml',
  'package-lock.json',
  'yarn.lock',
  'bun.lockb',
  'dist/',
  'build/',
  'artifacts/',
  '.tmp-main/',
  'out/',
  'coverage/',
  '*.min.js',
  '*.min.css',
  '*.bundle.js',
  '*.map',
  '*.svg',
  '*.png',
  '*.jpg',
  '*.jpeg',
  '*.gif',
  '*.ico',
  '*.webp',
  '*.pdf',
  '*.woff',
  '*.woff2',
  '*.ttf',
  '*.eot',
  '*.otf',
  '*.mp4',
  '*.webm',
  '*.zip',
  '*.tar.gz',
  '*.gz',
  '*.exe',
  '*.dll',
  '*.so',
  '*.dylib',
  '*.bin',
  '*.wasm',
  '*.snap'
];

type CompiledMatcher = {
  isWildcard: boolean;
  regex?: RegExp;
  pattern: string;
  normalizedPattern: string;
  isDirPattern: boolean;
};

export function extractFilePathFromDiffHeader(header: string): string | undefined {
  const gitMatch = header.match(/^diff --git a\/(.+?) b\/(.+)$/m);
  if (gitMatch) return gitMatch[2];

  const plusMatch = header.match(/^\+\+\+\s+b\/(.+)$/m);
  if (plusMatch) return plusMatch[1];

  const minusMatch = header.match(/^---\s+a\/(.+)$/m);
  if (minusMatch) return minusMatch[1];

  return undefined;
}

function isBinaryDiffChunk(chunk: string): boolean {
  if (/Binary files .* and .* differ/i.test(chunk)) return true;
  if (/GIT binary patch/i.test(chunk)) return true;
  if (chunk.includes('\0')) return true;
  return false;
}

function splitUnifiedDiffIntoBlocks(diffText: string): string[] {
  if (!diffText.trim()) return [];

  const lines = diffText.split('\n');
  const blocks: string[] = [];
  let currentBlock: string[] = [];

  for (const line of lines) {
    if ((line.startsWith('diff --git ') || line.startsWith('--- a/') || line.startsWith('--- /dev/null')) && currentBlock.length > 0) {
      blocks.push(currentBlock.join('\n'));
      currentBlock = [];
    }
    currentBlock.push(line);
  }

  if (currentBlock.length > 0) {
    blocks.push(currentBlock.join('\n'));
  }

  return blocks;
}

function isRelevantBusinessLogicOrContract(block: string, _filePath?: string): boolean {
  const lines = block.split('\n');
  const changedLines = lines.filter(l =>
    (l.startsWith('+') || l.startsWith('-')) &&
    !l.startsWith('+++') &&
    !l.startsWith('---')
  );

  if (changedLines.length === 0) {
    return true;
  }

  let isAssetBlob = false;
  for (const line of changedLines) {
    const content = line.slice(1).trim();
    if (content.startsWith('data:image/') || content.startsWith('data:font/')) {
      isAssetBlob = true;
      break;
    }
    if (content.length > 1000 && !content.includes(';') && !content.includes('{') && !content.includes('(')) {
      isAssetBlob = true;
      break;
    }
  }

  if (isAssetBlob) {
    return false;
  }

  return true;
}

/**
 * AST-aware pre-filter for unified diffs.
 * Automatically excludes lockfiles, build outputs, minified files, SVG/binary assets,
 * and generated non-code data blobs, focusing token budget strictly on modified
 * business logic and contracts.
 */
export function filterUnifiedDiffByAST(
  diffText: string,
  lowImpactPaths: string[] = DEFAULT_EXCLUDED_PATTERNS
): string {
  if (!diffText || typeof diffText !== 'string') {
    return '';
  }

  const blocks = splitUnifiedDiffIntoBlocks(diffText);
  const keptBlocks: string[] = [];

  for (const block of blocks) {
    const filePath = extractFilePathFromDiffHeader(block);

    if (filePath) {
      const filtered = filterLowImpactFiles([filePath], lowImpactPaths);
      if (filtered.length === 0) {
        continue;
      }
    }

    if (isBinaryDiffChunk(block)) {
      continue;
    }

    if (!isRelevantBusinessLogicOrContract(block, filePath)) {
      continue;
    }

    keptBlocks.push(block);
  }

  return keptBlocks.join('\n');
}

export const filterUnifiedDiff = filterUnifiedDiffByAST;

export function filterLowImpactFiles(files: string[], lowImpactPaths: string[] = DEFAULT_EXCLUDED_PATTERNS): string[] {
  if (!Array.isArray(files) || !Array.isArray(lowImpactPaths)) {
    throw new TypeError('Both files and lowImpactPaths must be arrays.');
  }
  const combinedPatterns = Array.from(new Set(lowImpactPaths));

  const matchers: CompiledMatcher[] = combinedPatterns.map(p => {
    if (p.includes('*')) {
      const regexPattern = p
        .replace(/[.+^${}()|[\]\\]/g, '\\$&')
        .replace(/\*/g, '.*');
      const regex = new RegExp(`(^|${path.sep === '\\' ? '\\\\' : path.sep})${regexPattern}$`, 'i');
      return { isWildcard: true, regex, pattern: p, normalizedPattern: '', isDirPattern: false };
    }

    let normalizedP = path.normalize(p);
    const isDirPattern = p.endsWith('/') || p.endsWith(path.sep);
    if (isDirPattern && !normalizedP.endsWith(path.sep)) {
      normalizedP += path.sep;
    }

    return { isWildcard: false, pattern: p, normalizedPattern: normalizedP, isDirPattern };
  });

  return files.filter(f => {
    const normalizedF = path.normalize(f);

    return !matchers.some(m => {
      if (m.isWildcard && m.regex) {
        return m.regex.test(normalizedF);
      }

      const { normalizedPattern, isDirPattern } = m;

      if (normalizedF === normalizedPattern) return true;

      if (isDirPattern) {
        return normalizedF.startsWith(normalizedPattern) || normalizedF.includes(path.sep + normalizedPattern);
      }

      return normalizedF === normalizedPattern || normalizedF.endsWith(path.sep + normalizedPattern);
    });
  });
}

/**
 * Truncates an AST/unified diff chunk by preserving file headers and diff hunk headers
 * (e.g. `diff --git`, `@@ -a,b +c,d @@`) while dropping middle lines if token/char limit is exceeded.
 */
export function truncateUnifiedDiff(diffText: string, maxChars: number = 16000): string {
  if (!diffText || diffText.length <= maxChars) {
    return diffText;
  }

  const lines = diffText.split('\n');
  const resultLines: string[] = [];
  let currentChars = 0;
  let isDroppingLines = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    const isHeader = line.startsWith('diff --git') ||
                     line.startsWith('--- ') ||
                     line.startsWith('+++ ') ||
                     line.startsWith('@@ ');

    if (currentChars + line.length + 1 > maxChars && !isHeader) {
      if (!isDroppingLines) {
        resultLines.push('...[DIFF TRUNCATED TO FIT TOKEN BUDGET]');
        isDroppingLines = true;
      }
      continue;
    }

    if (isHeader) {
      isDroppingLines = false;
    }

    resultLines.push(line);
    currentChars += line.length + 1;
  }

  return resultLines.join('\n');
}

export function calculateReviewHash(summary: CodeReviewSummary): string {
  const hash = crypto.createHash('sha256');
  const data = JSON.stringify({
    role: summary.role || '',
    diff: summary.diffContext || '',
    goal: summary.prGoal || '',
    external: summary.externalContext || '',
    semantic: summary.impactSemanticContext || '',
  });
  return hash.update(data).digest('hex');
}

export function pruneCache(
  cache: Record<string, CodeReviewResult>,
  maxEntries: number = 15
): Record<string, CodeReviewResult> {
  const safeMax = Math.max(0, Math.floor(maxEntries));
  if (safeMax === 0) return {};
  const keys = Object.keys(cache);
  if (keys.length <= safeMax) return cache;

  const newCache: Record<string, CodeReviewResult> = {};
  keys.slice(-safeMax).forEach(key => {
    newCache[key] = cache[key];
  });
  return newCache;
}

export function parseCodeReviewVerdict(feedback: string): 'pass' | 'fail' | 'warn' {
  if (typeof feedback !== 'string') return 'pass';
  const matches = Array.from(feedback.matchAll(/\[VERDICT:\s*(PASS|WARN|FAIL)\]/gi));
  if (matches.length > 0) {
    const lastMatch = matches[matches.length - 1][1].toUpperCase();
    if (lastMatch === 'FAIL') return 'fail';
    if (lastMatch === 'WARN') return 'warn';
    return 'pass';
  }

  return 'pass';
}

export function parseCodeReviewState(feedback: string): CodeReviewState | undefined {
  return parseCodeReviewStateDetailed(feedback).state;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function getSafeString(obj: Record<string, unknown>, key: string): string | undefined {
  const val = obj[key];
  return typeof val === 'string' ? val : undefined;
}

function getSafeNumber(obj: Record<string, unknown>, key: string): number | undefined {
  const val = obj[key];
  return typeof val === 'number' ? val : undefined;
}

function validateFindingsSchema(state: CodeReviewState): boolean {
  if (!state.findings || !Array.isArray(state.findings)) return false;
  return state.findings.every(f => {
    if (!isRecord(f)) return false;
    const id = getSafeString(f, 'id');
    const file = getSafeString(f, 'file');
    const issue = getSafeString(f, 'issue');
    const status = getSafeString(f, 'status');
    const confidence = getSafeString(f, 'confidence');
    return (
      id !== undefined && id.trim() !== '' &&
      file !== undefined && file.trim() !== '' &&
      issue !== undefined && issue.trim() !== '' &&
      (status === 'open' || status === 'resolved') &&
      (confidence === undefined || ['high', 'medium', 'low'].includes(confidence))
    );
  });
}

function normalizeFindings(findings: unknown[]): ReviewFinding[] {
  if (!Array.isArray(findings)) return [];
  return findings.map((f, idx) => {
    if (!isRecord(f)) {
      return {
        id: `finding-${idx}`,
        file: 'unknown',
        issue: 'Unspecified issue',
        status: 'open',
        confidence: 'medium'
      };
    }

    const id = getSafeString(f, 'id') ?? `finding-${idx}`;
    const file = getSafeString(f, 'file') ?? 'unknown';
    const issue = getSafeString(f, 'issue') ?? 'Unspecified issue';

    const rawStatus = getSafeString(f, 'status');
    const status = (rawStatus !== undefined && rawStatus.toLowerCase() === 'resolved') ? 'resolved' : 'open';

    const rawSeverity = getSafeString(f, 'severity');
    let severity: 'HIGH' | 'MEDIUM' | 'LOW' | undefined;
    if (rawSeverity !== undefined) {
      const lower = rawSeverity.toLowerCase();
      const severityMap: Record<string, 'HIGH' | 'MEDIUM' | 'LOW'> = {
        high: 'HIGH',
        medium: 'MEDIUM',
        low: 'LOW',
        error: 'HIGH',
        warn: 'MEDIUM',
        info: 'LOW'
      };
      if (lower in severityMap) {
        severity = severityMap[lower];
      }
    }

    const rawConfidence = getSafeString(f, 'confidence');
    let confidence: 'high' | 'medium' | 'low' = 'medium';
    if (rawConfidence !== undefined) {
      const lower = rawConfidence.toLowerCase();
      if (['high', 'medium', 'low'].includes(lower)) {
        confidence = lower as 'high' | 'medium' | 'low';
      }
    }

    const line = getSafeNumber(f, 'line');
    const startLine = getSafeNumber(f, 'startLine');
    const endLine = getSafeNumber(f, 'endLine');
    const snippet = getSafeString(f, 'snippet');
    const fixSummary = getSafeString(f, 'fixSummary');
    const counterexample = getSafeString(f, 'counterexample');
    const suggestion = getSafeString(f, 'suggestion');

    return {
      id,
      file,
      issue,
      status,
      severity,
      confidence,
      line,
      startLine,
      endLine,
      snippet,
      fixSummary,
      counterexample,
      suggestion,
    };
  });
}

const JSON_PATTERN = /\{[\s\S]*\}|\[[\s\S]*\]/;

function extractFindingsJsonText(feedback: string): { jsonText?: string; errors: CodeReviewParseError[] } {
  const openTag = '<findings>';
  const closeTag = '</findings>';

  const openIdx = feedback.lastIndexOf(openTag);
  const closeIdx = feedback.lastIndexOf(closeTag);
  const errors: CodeReviewParseError[] = [];

  const openedButNeverClosed = openIdx !== -1 && (closeIdx === -1 || closeIdx < openIdx);
  if (openedButNeverClosed) errors.push('missing_closing_tag');

  let jsonText: string;
  if (openIdx !== -1) {
    if (closeIdx !== -1 && closeIdx > openIdx) {
      jsonText = feedback.slice(openIdx + openTag.length, closeIdx).trim();
    } else {
      jsonText = feedback.slice(openIdx + openTag.length).trim();
    }
  } else {
    if (feedback.includes('{') || feedback.includes('[')) {
      jsonText = feedback.trim();
      if (!jsonText.startsWith('{') && !jsonText.startsWith('[')) {
        const extracted = jsonText.match(JSON_PATTERN);
        if (extracted) jsonText = extracted[0];
        else return { errors };
      }
    } else {
      return { errors };
    }
  }

  return { jsonText, errors };
}

function extractJsonBoundaries(jsonText: string): { boundedText: string; isTruncated: boolean } {
  const firstBrace = jsonText.indexOf('{');
  const firstBracket = jsonText.indexOf('[');
  const lastBrace = jsonText.lastIndexOf('}');
  const lastBracket = jsonText.lastIndexOf(']');

  let startIdx = -1;
  if (firstBrace !== -1 && (firstBracket === -1 || firstBrace < firstBracket)) {
    startIdx = firstBrace;
  } else if (firstBracket !== -1) {
    startIdx = firstBracket;
  }

  let endIdx = -1;
  if (lastBrace !== -1 && lastBrace > lastBracket) {
    endIdx = lastBrace;
  } else if (lastBracket !== -1) {
    endIdx = lastBracket;
  }

  const isTruncated = startIdx !== -1 && endIdx === -1;

  let boundedText: string;
  if (startIdx !== -1 && endIdx !== -1 && endIdx > startIdx) {
    boundedText = jsonText.slice(startIdx, endIdx + 1);
  } else if (isTruncated) {
    boundedText = jsonText.slice(startIdx);
  } else {
    boundedText = jsonText.replace(/^```[a-z]*\s*|\s*```$/gi, '').trim();
  }

  return { boundedText, isTruncated };
}

function parseAndSanitizeJson(jsonText: string): { parsedState: any; parseError?: CodeReviewParseError } {
  const sanitizedJsonText = jsonText
    .replace(/\\`/g, '`')
    .replace(/\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})/g, '\\\\');

  try {
    const state = JSON.parse(sanitizedJsonText);
    return { parsedState: state };
  } catch (e) {
    const salvaged = sanitizedJsonText.match(JSON_PATTERN);
    if (salvaged) {
      try {
        const state = JSON.parse(salvaged[0]);
        return { parsedState: state };
      } catch (e2) {
        return { parsedState: undefined, parseError: 'invalid_json' };
      }
    }
    return { parsedState: undefined, parseError: 'invalid_json' };
  }
}

export function parseCodeReviewStateDetailed(feedback: string): ParsedFindingsResult {
  const { jsonText, errors } = extractFindingsJsonText(feedback);

  if (!jsonText) {
    return { state: undefined };
  }

  const { boundedText, isTruncated } = extractJsonBoundaries(jsonText);
  if (isTruncated) errors.push('truncated_json');

  try {
    const { parsedState, parseError } = parseAndSanitizeJson(boundedText);
    if (parseError || !parsedState) {
      return { state: undefined, parseError: parseError || 'invalid_json' };
    }

    let state = parsedState;
    if (Array.isArray(state)) {
      state = { findings: state };
    }

    if (state && state.findings) {
      state.findings = normalizeFindings(state.findings);
    }

    if (!validateFindingsSchema(state as CodeReviewState)) {
      errors.push('incomplete_findings');
    }

    return {
      state: state as CodeReviewState,
      parseError: errors[0],
      errors: errors.length > 0 ? errors : undefined
    };
  } catch (e) {
    if (process.env.NODE_ENV !== 'test') {
      console.warn('Failed to parse findings JSON:', e, 'JSON snippet:', jsonText.slice(0, 100));
    }
    return { state: undefined, parseError: 'invalid_json' };
  }
}

export function estimateMaxOutputTokens(
  summary: CodeReviewSummary,
  _systemPromptLength: number = 0,
  thinkingBudget: number = 2048,
  outputPadding: number = 256
): number {
  const diffTokens = Math.ceil(summary.diffContext.length / 4);
  const estimatedOutput = Math.min(
    diffTokens * 0.4,
    2000,
  );

  const priorFindingsCount = summary.previousState?.findings.length ?? 0;
  const priorFindingsBudget = priorFindingsCount * 200;

  const totalBudget = Math.ceil(estimatedOutput + thinkingBudget + outputPadding + priorFindingsBudget);

  return Math.min(totalBudget, 8192);
}

export const EXTERNAL_CONTEXT_TRUNCATED_MESSAGE = '...[TRUNCATED EXTERNAL CONTEXT TO FIT TOKEN LIMIT]';
export const EXTERNAL_CONTEXT_MINIMUM_BUDGET = 200;

export function budgetInputContext(
  systemPrompt: string,
  summary: CodeReviewSummary,
  maxInputChars: number = 24000
): { diffText: string; externalText: string } {
  const remainingBudgetForDiffAndContext = Math.max(0, maxInputChars - systemPrompt.length);

  let rawDiffText = filterUnifiedDiffByAST(summary.diffContext);
  let rawExternalText = summary.externalContext || '';

  if (rawDiffText.length + rawExternalText.length > remainingBudgetForDiffAndContext) {
    const maxDiffChars = Math.max(0, Math.min(rawDiffText.length, 16000, remainingBudgetForDiffAndContext));
    if (rawDiffText.length > maxDiffChars) {
      rawDiffText = truncateUnifiedDiff(rawDiffText, maxDiffChars);
    }

    const remainingForExternal = remainingBudgetForDiffAndContext - rawDiffText.length;
    if (rawExternalText) {
      if (remainingForExternal >= EXTERNAL_CONTEXT_MINIMUM_BUDGET) {
        if (rawExternalText.length > remainingForExternal) {
          rawExternalText = rawExternalText.slice(0, remainingForExternal - 50) + '\n\n...[TRUNCATED TO FIT TOKEN LIMIT]';
        }
      } else {
        rawExternalText = EXTERNAL_CONTEXT_TRUNCATED_MESSAGE;
      }
    }
  }

  return { diffText: rawDiffText, externalText: rawExternalText };
}

export function calculateEstimatedTokens(text: string | string[]): number {
  const combined = Array.isArray(text) ? text.join('') : text;
  return Math.ceil(combined.length / 4);
}

export function extractFeedbackText(content: unknown): string {
  if (content === null || content === undefined) return '';
  let feedback: string;

  if (typeof content === 'string') {
    feedback = content.replace(/^\s*```(?:json|xml)?\s*\n/i, '').replace(/\n\s*```\s*$/i, '');
  } else if (Array.isArray(content)) {
    const textParts = content
      .filter((p: unknown) => {
        if (typeof p === 'object' && p !== null) {
          return !('thought' in p);
        }
        return true;
      })
      .map((p: unknown) => {
        if (typeof p === 'object' && p !== null && 'text' in p) {
          return String((p as Record<string, unknown>).text ?? '');
        }
        return '';
      })
      .filter(p => p !== '');

    if (textParts.length > 0) {
      feedback = textParts.join('');
    } else {
      feedback = JSON.stringify(content);
    }
  } else {
    feedback = JSON.stringify(content);
  }

  return feedback;
}

export function cleanupFeedback(feedback: string): string {
  let cleaned = feedback.replace(/<findings>[\s\S]*?<\/findings>/gi, '');
  cleaned = cleaned.replace(/\[VERDICT:\s*(PASS|WARN|FAIL)\]/gi, '');
  cleaned = cleaned.replace(/```(?:json|xml)?\s*\n\s*```/gi, '');
  return cleaned.replace(/\n{3,}/g, '\n\n').trim();
}

export function batchFiles(files: string[], maxBatchSize: number): string[][] {
  const batches: string[][] = [];
  for (let i = 0; i < files.length; i += maxBatchSize) {
    batches.push(files.slice(i, i + maxBatchSize));
  }
  return batches;
}

export type ReviewPayloadItem = { role: string; content: string };

export interface PayloadConfig {
  diffPrefix?: string;
  externalPrefix?: string;
}

export function buildReviewPayload(
  systemPrompt: string,
  diffText: string,
  externalText?: string,
  config: PayloadConfig = {}
): ReviewPayloadItem[] {
  const diffPrefix = config.diffPrefix ?? 'DIFF:\n\n';
  const externalPrefix = config.externalPrefix ?? 'EXTERNAL CONTEXT (Types/Interfaces/Constants referenced in the diff):\n\n';

  const payload: ReviewPayloadItem[] = [
    { role: 'system', content: systemPrompt },
    { role: 'user', content: `${diffPrefix}${diffText}` },
  ];

  if (externalText) {
    const formattedExternal = externalText === EXTERNAL_CONTEXT_TRUNCATED_MESSAGE
      ? externalText
      : `${externalPrefix}${externalText}`;
    payload.push({ role: 'system', content: formattedExternal });
  }

  return payload;
}

export async function withRetry<T>(
  fn: () => Promise<T>,
  options: {
    maxRetries?: number;
    initialDelayMs?: number;
    factor?: number;
    jitter?: boolean;
  } = {}
): Promise<T> {
  const maxRetries = options.maxRetries ?? 4;
  const initialDelayMs = options.initialDelayMs ?? 1000;
  const factor = options.factor ?? 2;
  const jitter = options.jitter ?? true;

  for (let attempt = 1; attempt <= maxRetries + 1; attempt++) {
    try {
      return await fn();
    } catch (error: unknown) {
      const isLastAttempt = attempt === maxRetries + 1;
      const errorMsg = error instanceof Error ? error.message : String(error);
      const isRateLimit = errorMsg.includes('429') ||
                          errorMsg.toLowerCase().includes('rate limit') ||
                          errorMsg.toLowerCase().includes('resource_exhausted') ||
                          errorMsg.includes('RESOURCE_EXHAUSTED');
      const isTransient = isRateLimit ||
                          errorMsg.includes('500') ||
                          errorMsg.includes('502') ||
                          errorMsg.includes('503') ||
                          errorMsg.includes('504') ||
                          errorMsg.toLowerCase().includes('econnreset') ||
                          errorMsg.toLowerCase().includes('socket timeout') ||
                          errorMsg.toLowerCase().includes('fetch failed') ||
                          errorMsg.toLowerCase().includes('timeout');

      if (isLastAttempt || !isTransient) {
        throw error;
      }

      const backoffDelay = initialDelayMs * Math.pow(factor, attempt - 1);
      const actualDelay = jitter ? backoffDelay * (0.5 + Math.random() * 0.5) : backoffDelay;

      console.warn(`⚠️ Attempt ${attempt} failed: ${errorMsg}. Retrying in ${Math.round(actualDelay)}ms (Rate Limit: ${isRateLimit})...`);

      await new Promise(resolve => setTimeout(resolve, actualDelay));
    }
  }
  throw new Error('Unreachable code in withRetry');
}
