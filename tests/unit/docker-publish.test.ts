import { describe, expect, it } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';
import yaml from 'yaml';

describe('Publish Runner Workflow Validation', () => {
  it('should contain metadata-action configured for latest alias on main branch', () => {
    const workflowPath = path.join(__dirname, '../../.github/workflows/publish-runner.yml');
    const content = fs.readFileSync(workflowPath, 'utf-8');
    const parsed = yaml.parse(content);

    const steps = parsed.jobs['publish-docker'].steps;
    const metaStep = steps.find((s: { id?: string }) => s.id === 'meta');

    expect(metaStep).toBeDefined();
    expect(metaStep.uses).toContain('docker/metadata-action');
    expect(metaStep.with.tags).toContain('type=raw,value=latest,enable=${{ github.ref == \'refs/heads/main\' }}');
  });
});
