import * as path from 'path';
import * as crypto from 'crypto';
import type { CodeReviewSummary, CodeReviewState, ParsedFindingsResult, CodeReviewResult } from './codeReviewTypes';

/**
 * Generates a stable SHA-256 hash for a code review batch.
 * Includes diff context, role, goal, and all relevant semantic/external context.
 * Explicitly handles undefined values to ensure stable serialization.
 */
export function filterLowImpactFiles(files: string[], lowImpactPaths: string[]): string[] {
  if (!Array.isArray(files) || !Array.isArray(lowImpactPaths)) {
    throw new TypeError('Both files and lowImpactPaths must be arrays.');
  }
  return files.filter(f => {
    return !lowImpactPaths.some(p => {
      // Normalize to handle mixed slashes and dot segments safely
      const normalizedF = path.normalize(f);
      let normalizedP = path.normalize(p);

      // Handle exact matches
      if (normalizedF === normalizedP) return true;

      // Ensure directory patterns check correctly
      const isDirPattern = p.endsWith('/') || p.endsWith(path.sep);
      if (isDirPattern) {
        if (!normalizedP.endsWith(path.sep)) {
          normalizedP += path.sep;
        }
        // It must start with the directory pattern, OR the directory pattern must be preceded by a path separator.
        // And since normalizedP already ends with a path separator, we know it's matching a full directory.
        return normalizedF.startsWith(normalizedP) || normalizedF.includes(path.sep + normalizedP);
      }

      // Handle file matches (e.g., packages/web/pnpm-lock.yaml matching pnpm-lock.yaml)
      // Must be an exact match or preceded by a path separator to avoid partial name matches
      return normalizedF === normalizedP || normalizedF.endsWith(path.sep + normalizedP);
    });
  });
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

/**
 * Prunes a cache object to maintain a maximum number of entries.
 * Since GitHub comments have a 65,536 character limit, we must cap the state.
 * This implementation keeps the most recently added N entries (insertion order).
 */
export function pruneCache(
  cache: Record<string, CodeReviewResult>,
  maxEntries: number = 15
): Record<string, CodeReviewResult> {
  const safeMax = Math.max(0, Math.floor(maxEntries));
  if (safeMax === 0) return {};
  const keys = Object.keys(cache);
  if (keys.length <= safeMax) return cache;

  const newCache: Record<string, CodeReviewResult> = {};
  // Keep the most recently added entries (the end of the keys array)
  // String keys in JS objects follow insertion order for slice/iteration.
  keys.slice(-safeMax).forEach(key => {
    newCache[key] = cache[key];
  });
  return newCache;
}

export function parseCodeReviewVerdict(feedback: string): 'pass' | 'fail' | 'warn' {
  const matches = [...feedback.matchAll(/\[VERDICT:\s*(PASS|WARN|FAIL)\]/gi)];
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

/**
 * Validates the findings schema to ensure all required fields are present.
 * Performs deep type checking to avoid runtime crashes on malformed LLM output.
 */
function validateFindingsSchema(state: CodeReviewState): boolean {
  if (!state.findings || !Array.isArray(state.findings)) return false;
  return state.findings.every(f =>
    f &&
    typeof f === 'object' &&
    typeof f.id === 'string' && f.id.trim() !== '' &&
    typeof f.file === 'string' && f.file.trim() !== '' &&
    typeof f.issue === 'string' && f.issue.trim() !== '' &&
    (f.status === 'open' || f.status === 'resolved') &&
    (f.confidence === undefined || ['high', 'medium', 'low'].includes(f.confidence))
  );
}

/**
 * Normalizes a list of findings by injecting default values for missing or malformed fields.
 * Ensures the resulting objects adhere to the ReviewFinding interface.
 */
export function normalizeFindings(findings: unknown[]): ReviewFinding[] {
  if (!Array.isArray(findings)) return [];
  return findings.map((f, idx) => {
    if (!f || typeof f !== 'object') return f;
    return {
      id: typeof f.id === 'string' ? f.id : `finding-${idx}`,
      file: typeof f.file === 'string' ? f.file : 'unknown',
      issue: typeof f.issue === 'string' ? f.issue : 'Unspecified issue',
      status: (typeof f.status === 'string' && f.status.toLowerCase() === 'resolved') ? 'resolved' : 'open',
      severity: (typeof f.severity === 'string' && ['error', 'warn', 'info', 'high', 'medium', 'low'].includes(f.severity.toLowerCase()))
        ? f.severity.toUpperCase() as 'HIGH' | 'MEDIUM' | 'LOW'
        : undefined,
      confidence: (typeof f.confidence === 'string' && ['high', 'medium', 'low'].includes(f.confidence.toLowerCase()))
        ? f.confidence.toLowerCase() as 'high' | 'medium' | 'low'
        : 'medium',
      line: typeof f.line === 'number' ? f.line : undefined,
      snippet: typeof f.snippet === 'string' ? f.snippet : undefined,
      fixSummary: typeof f.fixSummary === 'string' ? f.fixSummary : undefined,
      counterexample: typeof f.counterexample === 'string' ? f.counterexample : undefined,
    };
  });
}

export function parseCodeReviewStateDetailed(feedback: string): ParsedFindingsResult {
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
      // Filter out non-JSON strings that just happen to include brackets
      if (!jsonText.startsWith('{') && !jsonText.startsWith('[')) {
        const extracted = jsonText.match(/\{[\s\S]*\}|\[[\s\S]*\]/);
        if (extracted) jsonText = extracted[0];
        else return { state: undefined };
      }
    } else {
      return { state: undefined };
    }
  }

  // Robust extraction: find the boundaries of the outermost JSON object or array
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
  if (isTruncated) errors.push('truncated_json');

  if (startIdx !== -1 && endIdx !== -1 && endIdx > startIdx) {
    jsonText = jsonText.slice(startIdx, endIdx + 1);
  } else if (isTruncated) {
    jsonText = jsonText.slice(startIdx);
  } else {
    // Strip markdown code blocks if boundaries weren't found
    jsonText = jsonText.replace(/^```[a-z]*\s*/gi, '').replace(/\s*```$/g, '').trim();
    if (!jsonText.startsWith('{') && !jsonText.startsWith('[')) {
      return { state: undefined };
    }
  }

  try {
    // Pre-process jsonText to fix any unescaped backslashes (e.g. \s, \d, \w, paths)
    // by escaping them (replacing \ with \\ if not followed by valid JSON escape character)
    // Additionally fix \` that might be incorrectly escaped by the model
    let sanitizedJsonText = jsonText.replace(/\\`/g, '`');
    sanitizedJsonText = sanitizedJsonText.replace(/\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})/g, '\\\\');
    let state;
    let lastErr;
    try {
      state = JSON.parse(sanitizedJsonText) as CodeReviewState;
    } catch (e) {
      lastErr = e;
      // Attempt to salvage finding parsing from markdown wrap bugs or prefix bugs
      const salvaged = sanitizedJsonText.match(/\{[\s\S]*\}|\[[\s\S]*\]/);
      if (salvaged) {
         try { state = JSON.parse(salvaged[0]); }
         catch (e2) { return { state: undefined }; }
      }
      else return { state: undefined };
    }

    if (state && state.findings) {
      state.findings = normalizeFindings(state.findings);
    }

    if (!validateFindingsSchema(state)) {
      errors.push('incomplete_findings');
    }

    return {
      state,
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
  // Thinking tokens consume the same budget as output tokens.
  // Add padding for JSON findings block and verdict line.
  const diffTokens = Math.ceil(summary.diffContext.length / 4);
  const estimatedOutput = Math.min(
    diffTokens * 0.4,  // heuristic: review output ~40% of diff size
    2000,              // cap — reviews shouldn't exceed this
  );

  const priorFindingsCount = summary.previousState?.findings.length ?? 0;
  const priorFindingsBudget = priorFindingsCount * 200;

  const totalBudget = Math.ceil(estimatedOutput + thinkingBudget + outputPadding + priorFindingsBudget);

  // Hard ceiling — raised to match what the models actually support
  return Math.min(totalBudget, 8192);
}

export const EXTERNAL_CONTEXT_TRUNCATED_MESSAGE = '...[TRUNCATED EXTERNAL CONTEXT TO FIT TOKEN LIMIT]';
export const EXTERNAL_CONTEXT_MINIMUM_BUDGET = 200;

export function budgetInputContext(
  systemPrompt: string,
  summary: CodeReviewSummary,
  maxInputChars: number = 24000
): { diffText: string; externalText: string } {
  // System prompt is essential. Let's see how much budget is left.
  const remainingBudgetForDiffAndContext = Math.max(0, maxInputChars - systemPrompt.length);

  let rawDiffText = summary.diffContext;
  let rawExternalText = summary.externalContext || '';

  if (rawDiffText.length + rawExternalText.length > remainingBudgetForDiffAndContext) {
    // Allocate the remaining budget between diff and external context.
    // Diff gets priority: up to 16,000 characters, capped at remaining budget.
    const maxDiffChars = Math.max(0, Math.min(rawDiffText.length, 16000, remainingBudgetForDiffAndContext));
    if (rawDiffText.length > maxDiffChars) {
      rawDiffText = rawDiffText.slice(0, maxDiffChars) + '\n\n...[TRUNCATED TO FIT TOKEN LIMIT]';
    }

    const remainingForExternal = remainingBudgetForDiffAndContext - rawDiffText.length;
    if (rawExternalText) {
      if (remainingForExternal > EXTERNAL_CONTEXT_MINIMUM_BUDGET) {
        if (rawExternalText.length > remainingForExternal) {
          rawExternalText = rawExternalText.slice(0, remainingForExternal - 50) + '\n\n...[TRUNCATED TO FIT TOKEN LIMIT]';
        }
      } else {
        // Harden: ensure we don't just drop the context entirely without notice
        rawExternalText = EXTERNAL_CONTEXT_TRUNCATED_MESSAGE;
      }
    }
  }

  return { diffText: rawDiffText, externalText: rawExternalText };
}

/**
 * Heuristic: 1 token is roughly 4 characters.
 */
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
      .filter(p => p !== ''); // Only keep actual text parts

    if (textParts.length > 0) {
      feedback = textParts.join('');
    } else {
      feedback = JSON.stringify(content); // Fallback to full JSON stringification if no text parts
    }
  } else {
    feedback = JSON.stringify(content);
  }

  return feedback;
}

/**
 * Strips machine-readable tags like <findings> and [VERDICT] from the feedback.
 */
export function cleanupFeedback(feedback: string): string {
  let cleaned = feedback.replace(/<findings>[\s\S]*?<\/findings>/gi, '');
  cleaned = cleaned.replace(/\[VERDICT:\s*(PASS|WARN|FAIL)\]/gi, '');
  // Collapse multiple newlines into two and trim
  return cleaned.replace(/\n{3,}/g, '\n\n').trim();
}

/**
 * Split a list of files into batches of a certain size.
 */
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

/**
 * Builds the standard payload for code review models using direct REST API role structure.
 */
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
    // Using a separate system message for symbol resolution context ensures it's treated
    // as context mapping rather than part of the user's diff input
    payload.push({ role: 'system', content: formattedExternal });
  }

  return payload;
}

/**
 * Reusable exponential backoff with jitter retry wrapper.
 * Targets rate limits (429 / resource exhausted) and transient server errors (500, 502, 503, 504).
 */
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
