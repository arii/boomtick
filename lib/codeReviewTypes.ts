export interface ReviewFinding {
  id: string;
  file: string;
  issue: string;
  status: 'open' | 'resolved';
  severity?: 'HIGH' | 'MEDIUM' | 'LOW';
  confidence: 'high' | 'medium' | 'low';
  line?: number;
  snippet?: string;
  fixSummary?: string;
  counterexample?: string;
}

export interface CodeReviewState {
  findings: ReviewFinding[];
}

export type CodeReviewParseError = 'missing_closing_tag' | 'truncated_json' | 'incomplete_findings' | 'invalid_json';

export interface ParsedFindingsResult {
  state?: CodeReviewState;
  parseError?: CodeReviewParseError;
  errors?: CodeReviewParseError[];
}

export interface CodeReviewSummary {
  role: string;
  diffContext: string;
  prGoal: string;
  externalContext?: string;
  impactSemanticContext?: string;
  previousState?: CodeReviewState;
}

export interface ModelChain {
  primary: string;
  fallbacks: string[];
  max_retries: number;
}

export interface CodeReviewResult {
  feedback: string;
  role: string;
  tokens: number;
  cost: number;
  modelName: string;
  findings: ReviewFinding[];
  llmVerdict: 'pass' | 'warn' | 'fail';
  isTruncated?: boolean;
}
