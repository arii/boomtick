export interface ReviewFinding {
  id: string;
  file: string;
  issue: string;
  status: 'open' | 'resolved';
  severity?: 'HIGH' | 'MEDIUM' | 'LOW' | 'error' | 'warn' | 'info';
  confidence: 'high' | 'medium' | 'low';
  line?: number;
  startLine?: number;
  endLine?: number;
  snippet?: string;
  fixSummary?: string;
  counterexample?: string;
  suggestion?: string;
}

export type CodeReviewRole = 'SECURITY' | 'PERFORMANCE' | 'STYLE' | 'ARCHITECTURE';

export interface CodeReviewState {
  findings: ReviewFinding[];
  cache?: { [key: string]: CodeReviewResult };
}

export type CodeReviewParseError = 'missing_closing_tag' | 'truncated_json' | 'incomplete_findings' | 'invalid_json';

export interface ParsedFindingsResult {
  state?: CodeReviewState;
  parseError?: CodeReviewParseError;
  errors?: CodeReviewParseError[];
}

export interface CodeReviewSummary {
  role?: string;
  diffContext: string;
  prGoal?: string;
  fullDiff?: string;
  changedFiles?: string[];
  diffStat?: string;
  isTruncated?: boolean;
  externalContext?: string;
  impactSemanticContext?: string;
  previousState?: CodeReviewState;
  estimatedInputTokens?: number;
}

// fallow-ignore-next-line unused-type
export interface IssueSummary {
  number: number;
  title: string;
  html_url: string;
  state: string;
}

export interface CodeReviewResult extends CodeReviewState {
  feedback: string;
  role?: string;
  tokens: number;
  cost: number;
  modelName: string;
  llmVerdict: 'pass' | 'warn' | 'fail';
  /** Modern standard field indicating if the LLM output was truncated */
  isTruncated?: boolean;
  state?: CodeReviewState;
  skipReason?: string;
  inputTokens?: number;
  outputTokens?: number;
  cacheTokens?: number;
  parseError?: CodeReviewParseError;
}
