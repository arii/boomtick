import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as fs from 'fs';
import { orchestrateVisualReview } from '../../lib/visualReviewOrchestrator';

vi.mock('fs', () => ({
  existsSync: vi.fn(),
  readFileSync: vi.fn(),
  writeFileSync: vi.fn(),
}));

vi.mock('../../lib/visualReviewUtils', () => ({
  generateMarkdownReport: vi.fn(() => 'mock report'),
  postPRComment: vi.fn(),
  countExistingReviews: vi.fn().mockResolvedValue(0),
  getJulesSessionIdFromPR: vi.fn().mockResolvedValue(null),
  sendJulesMessage: vi.fn(),
  getPreviousReviewState: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../../lib/aiLogger', () => ({
  logReviewExecution: vi.fn(),
}));

describe('visualReviewOrchestrator - Concurrency limit', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('respects the CONCURRENCY_LIMIT of 2 and correctly processes all tasks', async () => {
    const mockSummary = {
      routes: [
        { route: '/home', differencePercent: 12.5, severity: 'HIGH', slug: 'home' },
        { route: '/about', differencePercent: 5.0, severity: 'MEDIUM', slug: 'about' }
      ]
    };

    vi.mocked(fs.existsSync).mockImplementation((p: any) => {
      if (typeof p === 'string' && p.includes('summary.json')) {
        return true;
      }
      return false;
    });

    vi.mocked(fs.readFileSync).mockImplementation((p: any) => {
      if (typeof p === 'string' && p.includes('summary.json')) {
        return JSON.stringify(mockSummary);
      }
      return '';
    });

    let activeRequests = 0;
    let maxActiveRequests = 0;
    const invokedTasks: { route: string; role: string }[] = [];

    const mockClient = {
      botName: 'mock-bot',
      reportTitle: 'Mock Report',
      botTagline: 'Mock Tagline',
      reportFileName: 'mock-report.md',
      invokeReview: vi.fn().mockImplementation(async (summary, role) => {
        activeRequests++;
        maxActiveRequests = Math.max(maxActiveRequests, activeRequests);
        invokedTasks.push({ route: summary.route, role });

        // Add a slight delay to allow concurrency to build up
        await new Promise(resolve => setTimeout(resolve, 50));

        activeRequests--;
        return {
          route: summary.route,
          severity: summary.severity,
          differencePercent: summary.differencePercent,
          feedback: 'Nice visual style',
          tokens: 100,
          cost: 0,
          modelName: 'mock-model',
          llmVerdict: 'pass',
          findings: []
        };
      })
    };

    await orchestrateVisualReview(mockClient);

    // Verify all 10 roles (2 routes * 5 roles) were processed
    expect(invokedTasks).toHaveLength(10);

    // Verify that the concurrency limit of 2 was strictly respected
    expect(maxActiveRequests).toBeLessThanOrEqual(2);
  });
});
