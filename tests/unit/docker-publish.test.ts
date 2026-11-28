import { describe, expect, it } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';
import yaml from 'yaml';

describe('Publish Runner Workflow Validation', () => {
  it('should contain metadata-action configured for latest alias on main branch', () => {
    const workflowPath = path.join(__dirname, '../../.github/workflows/publish-runner.yml');
    const content = fs.readFileSync(workflowPath, 'utf-8');
    const parsed = yaml.parse(content);

    const steps = (parsed.jobs['publish-docker'] || parsed.jobs['publish-artifacts']).steps;
    const metaStep = steps.find((s: { id?: string }) => s.id === 'meta');

    expect(metaStep).toBeDefined();
    expect(metaStep.uses).toContain('docker/metadata-action');
    expect(metaStep.with.tags).toContain('type=raw,value=latest,enable=${{ github.ref == \'refs/heads/main\' }}');
  });

  it('should contain step asserting zero Python binaries and size budget in container image', () => {
    const workflowPath = path.join(__dirname, '../../.github/workflows/publish-runner.yml');
    const content = fs.readFileSync(workflowPath, 'utf-8');
    const parsed = yaml.parse(content);

    const steps = (parsed.jobs['publish-docker'] || parsed.jobs['publish-artifacts']).steps;
    const verifyStep = steps.find((s: { name?: string }) => s.name === 'Verify Container Pure-Node Footprint & Size Budget');

    expect(verifyStep).toBeDefined();
    expect(verifyStep.run).toContain('command -v python || command -v python3');
    expect(verifyStep.run).toContain('boomtick-review:test');
  });
  it('should not mask registry publish failures and should verify each registry after publishing', () => {
    const workflowPath = path.join(__dirname, '../../.github/workflows/publish-runner.yml');
    const parsed = yaml.parse(fs.readFileSync(workflowPath, 'utf-8'));
    const steps: Array<{ name?: string; 'continue-on-error'?: boolean }> = (parsed.jobs['publish-docker'] || parsed.jobs['publish-artifacts']).steps;

    for (const name of ['Publish MCP to npm', 'Publish CLI to PyPI']) {
      const step = steps.find((s) => s.name === name);
      expect(step, name).toBeDefined();
      expect(step?.['continue-on-error'], name).toBeUndefined();
    }
    expect(steps.find((s) => s.name === 'Verify MCP version is on npm')).toBeDefined();
    expect(steps.find((s) => s.name === 'Verify CLI version is on PyPI')).toBeDefined();
  });
});
