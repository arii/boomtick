import { describe, expect, it } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';
import yaml from 'yaml';

describe('Standalone Migration Verification', () => {
  it('should verify project_config.json contains required vite_base_path', () => {
    const configPath = path.join(process.cwd(), 'project_config.json');
    const content = fs.readFileSync(configPath, 'utf-8');
    const parsed = JSON.parse(content);

    expect(parsed).toHaveProperty('packageName');
    expect(parsed).toHaveProperty('github_repo');
    expect(parsed).toHaveProperty('vite_base_path');
    expect(typeof parsed.vite_base_path).toBe('string');
  });

  it('should ensure consumer workflow uses remote composite action without submodule checkouts', () => {
    const workflowPath = path.join(process.cwd(), '.github/workflows/ci.yml');
    const content = fs.readFileSync(workflowPath, 'utf-8');
    const parsed = yaml.parse(content);

    const steps = parsed.jobs['validate-and-analyze'].steps;
    const impactStep = steps.find((s: { name?: string }) => s.name === 'Run Standalone Impact Analysis');

    expect(impactStep).toBeDefined();
    expect(impactStep.uses).toMatch(/^arii\/boomtick\/\.github\/actions\/impact-analysis@/);

    // Ensure no sub-checkout steps for arii/boomtick exist in the steps array
    const stepsStr = JSON.stringify(steps);
    expect(stepsStr).not.toContain('repository: arii/boomtick');
    expect(stepsStr).not.toContain('path: boomtick');
  });
});
