export interface ReviewFinding {
  id: string;
  file: string;
  line?: number;
  snippet?: string;
  issue: string;
  status: 'open' | 'resolved';
  fixSummary?: string;
  severity?: 'error' | 'warn' | 'info' | 'HIGH' | 'MEDIUM' | 'LOW';
  confidence?: 'high' | 'medium' | 'low';
  counterexample?: string;
}

export interface CodeReviewState {
  findings: ReviewFinding[];
  cache?: Record<string, CodeReviewResult>;
}

export type CodeReviewRole = 'SECURITY' | 'PERFORMANCE' | 'STYLE' | 'ARCHITECTURE';

export interface CodeReviewSummary {
  diffContext: string;
  role?: CodeReviewRole;
  fullDiff?: string;
  prGoal?: string;
  changedFiles?: string[];
  externalContext?: string;
  impactSemanticContext?: string;
  previousState?: CodeReviewState;
  estimatedInputTokens?: number;
  isTruncated?: boolean;
  diffStat?: string;
}

export type CodeReviewParseError = 'missing_closing_tag' | 'invalid_json' | 'incomplete_findings' | 'truncated_json';

export interface ParsedFindingsResult {
  state?: CodeReviewState;
  parseError?: CodeReviewParseError;
  errors?: CodeReviewParseError[];
}

export interface CodeReviewResult {
  feedback: string;
  role?: CodeReviewRole;
  tokens: number;
  inputTokens?: number;
  outputTokens?: number;
  cacheTokens?: number;
  cost: number;
  llmVerdict?: 'pass' | 'fail' | 'warn';
  state?: CodeReviewState;
  modelName?: string;
  truncated?: boolean;
  skipReason?: string;
  parseError?: CodeReviewParseError;
  errors?: CodeReviewParseError[];
}
