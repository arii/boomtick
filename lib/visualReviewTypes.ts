export interface VisualReviewFinding {
  id: string;
  route: string;
  issue: string;
  status: 'open' | 'resolved';
  fixSummary?: string;
}

export interface VisualReviewState {
  findings: VisualReviewFinding[];
}

export interface VisualRouteSummary {
  route: string;
  slug: string;
  differencePercent: number;
  severity: 'LOW' | 'MEDIUM' | 'HIGH';
  beforeCroppedPath?: string;
  afterCroppedPath?: string;
  diffCroppedPath?: string;
  beforePath: string;
  afterPath: string;
  diffPath?: string;
  previousFindings?: VisualReviewFinding[];
  validation?: {
    passed: boolean;
    reason?: string;
  };
  metrics?: {
    before: {
      scrollWidth: number;
      mainWidth: number;
      scrollHeight: number;
    };
    after: {
      scrollWidth: number;
      mainWidth: number;
      scrollHeight: number;
      viewportWidth: number;
    };
  };
  tokens?: number;
}

export interface VisualSummary {
  routes: VisualRouteSummary[];
}

export interface RouteReview {
  route: string;
  severity: 'LOW' | 'MEDIUM' | 'HIGH';
  differencePercent: number;
  feedback: string;
  tokens: number;
  inputTokens?: number;
  outputTokens?: number;
  cacheTokens?: number;
  cost: number;
  modelName?: string;
  llmVerdict?: 'pass' | 'fail' | 'warn';
  findings?: VisualReviewFinding[];
  truncated?: boolean;
  role?: string;
}
