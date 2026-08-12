import { describe, expect, it } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';
import yaml from 'yaml';

describe('Composite Action Manifest', () => {
  it('should define a valid composite action without local submodule checkout steps', () => {
    const actionPath = path.join(__dirname, '../../.github/actions/impact-analysis/action.yml');
    const content = fs.readFileSync(actionPath, 'utf-8');
    const parsed = yaml.parse(content);

    expect(parsed.runs.using).toBe('composite');
    expect(parsed.inputs).toHaveProperty('github_token');

    const stepsStr = JSON.stringify(parsed.runs.steps);
    expect(stepsStr).not.toContain('actions/checkout');
    expect(stepsStr).not.toContain('actions/create-github-app-token');
  });
});