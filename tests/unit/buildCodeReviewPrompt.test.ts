import { describe, it, expect } from 'vitest';
import { buildSystemPrompt } from '../../lib/buildCodeReviewPrompt';

describe('buildCodeReviewPrompt', () => {
  it('injects CI/CD guidance when .github/workflows file is changed', () => {
    const prompt = buildSystemPrompt({
      diffContext: 'some diff',
      changedFiles: ['.github/workflows/ci.yml']
    });
    expect(prompt).toContain('CATEGORY-SPECIFIC GUIDANCE:');
    expect(prompt).toContain('CI/CD:');
    expect(prompt).toContain('if: always()');
  });

  it('injects React guidance when .tsx file is changed', () => {
    const prompt = buildSystemPrompt({
      diffContext: 'some diff',
      changedFiles: ['src/components/Button.tsx']
    });
    expect(prompt).toContain('CATEGORY-SPECIFIC GUIDANCE:');
    expect(prompt).toContain('React:');
    expect(prompt).toContain('Blocking: hook rule violations');
  });

  it('injects LLM integration guidance when CodeReviewClient is changed', () => {
    const prompt = buildSystemPrompt({
      diffContext: 'some diff',
      changedFiles: ['scripts/clients/githubModelsCodeReviewClient.ts']
    });
    expect(prompt).toContain('CATEGORY-SPECIFIC GUIDANCE:');
    expect(prompt).toContain('LLM Clients:');
    expect(prompt).toContain('ChatOpenAI');
  });

  it('concatenates multiple guidance blocks if multiple categories match', () => {
    const prompt = buildSystemPrompt({
      diffContext: 'some diff',
      changedFiles: ['src/components/Button.tsx', '.github/workflows/ci.yml']
    });
    expect(prompt).toContain('CI/CD:');
    expect(prompt).toContain('React:');
  });

  it('does not include category guidance section if no categories match', () => {
    const prompt = buildSystemPrompt({
      diffContext: 'some diff',
      changedFiles: ['README.md']
    });
    expect(prompt).not.toContain('CATEGORY-SPECIFIC GUIDANCE:');
  });

  it('handles missing changedFiles gracefully', () => {
    const prompt = buildSystemPrompt({
      diffContext: 'some diff'
    });
    expect(prompt).not.toContain('CATEGORY-SPECIFIC GUIDANCE:');
  });

  it('contains false-positive placeholder guidelines for utility scripts', () => {
    const prompt = buildSystemPrompt({
      diffContext: 'some diff',
      changedFiles: ['scripts/utility.sh']
    });
    expect(prompt).toContain('PLACEHOLDER EXEMPTION:');
    expect(prompt).toContain('repos/{owner}/{repo}');
    expect(prompt).toContain('NEVER flag');
  });

  it('contains the explicit evidentiary and non-speculative guidelines for HIGH/blocking severity', () => {
    const prompt = buildSystemPrompt({
      diffContext: 'some diff',
      changedFiles: ['src/components/Button.tsx']
    });
    expect(prompt).toContain('High/Blocking: A blocking concern must point to a concrete contradiction in the diff itself');
    expect(prompt).toContain("A value passed where the type doesn't allow it");
    expect(prompt).toContain("No Speculation: Concerns phrased with speculative hedging language");
    expect(prompt).toContain('Verification: Reviewers must not raise concerns they cannot verify');
  });
});
