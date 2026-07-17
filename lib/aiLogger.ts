import * as fs from 'fs';
import * as path from 'path';

/**
 * Records an AI review run entry to a structured JSON Lines (.jsonl) log file.
 * This provides O(1) performance and ensures efficiency as logs accumulate.
 */
export interface AIRunLogEntry {
  timestamp: string;
  type: 'code-review' | 'visual-review';
  model?: string;
  inputTokens: number;
  outputTokens: number;
  cacheTokens?: number;
  totalTokens?: number;
  durationMs: number;
  cost: number;
  verdict?: string;
  pr?: string;
  route?: string;
  error?: string;
  truncated?: boolean;
  parseError?: string;
  rawResponse?: string;
  findings?: unknown[];
  inputChars?: number;
}

const LOG_DIR = path.join(process.cwd(), '.boomtick', 'logs', 'ai');
const LOG_FILE = path.join(LOG_DIR, 'review-run.jsonl');



export function logAIRun(entry: Omit<AIRunLogEntry, 'timestamp'>): void {
  try {
    if (!fs.existsSync(LOG_DIR)) {
      fs.mkdirSync(LOG_DIR, { recursive: true });
    }

    const logEntry: AIRunLogEntry = {
      timestamp: new Date().toISOString(),
      ...entry,
    };

    // Append as a single JSON line for performance
    fs.appendFileSync(LOG_FILE, JSON.stringify(logEntry) + '\n');
  } catch (error) {
    console.error('❌ Failed to append to AI run log:', error);
  }
}

interface ReviewResultLike {
  tokens: number;
  inputTokens?: number;
  outputTokens?: number;
  cacheTokens?: number;
  cost: number;
  modelName?: string;
  llmVerdict?: string;
  truncated?: boolean;
  parseError?: string;
  feedback: string;
  state?: { findings: unknown[] };
  findings?: unknown[];
}

/**
 * Unified helper to log review results from various orchestrators.
 */
export function logReviewExecution(
  type: AIRunLogEntry['type'],
  result: ReviewResultLike,
  durationMs: number,
  additional: { pr?: string; route?: string; inputChars?: number } = {}
): void {
  logAIRun({
    type,
    model: result.modelName || 'unknown',
    inputTokens: result.inputTokens ?? 0,
    outputTokens: result.outputTokens ?? 0,
    cacheTokens: result.cacheTokens ?? 0,
    totalTokens: result.tokens,
    durationMs,
    cost: result.cost,
    verdict: result.llmVerdict || 'unknown',
    pr: additional.pr || process.env.PR_NUMBER,
    route: additional.route,
    truncated: result.truncated,
    parseError: result.parseError,
    rawResponse: result.feedback,
    findings: result.findings || result.state?.findings,
    inputChars: additional.inputChars,
  });
}
