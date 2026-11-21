import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import yaml from 'yaml';

const root = path.resolve(__dirname, '../..');
const workflow = yaml.parse(fs.readFileSync(path.join(root, '.github/workflows/smoke-test-impact-analysis.yml'), 'utf8'));
const steps = workflow.jobs['smoke-test'].steps;

describe('deterministic Smoke wiring preserves integration boundaries', () => {
  it('retains the image, token and real composite path without pretending a fake key is approval', () => {
    expect(steps.find((step: any) => step.id === 'app-token').uses).toBe('./.github/actions/generate-token');
    expect(steps.some((step: any) => step.uses === 'docker/setup-buildx-action@v4')).toBe(true);
    expect(steps.some((step: any) => step.uses === 'docker/login-action@v4')).toBe(true);
    const build = steps.find((step: any) => step.uses === 'docker/build-push-action@v7');
    expect(build.with).toMatchObject({ push: false, load: true, tags: 'ghcr.io/arii/boomtick:${{ github.sha }}' });
    const action = steps.find((step: any) => step.uses === './.github/actions/impact-analysis');
    expect(action.with).toEqual({
      github_token: '${{ steps.app-token.outputs.token }}',
      'pr-number': '${{ inputs.pr-number }}',
      container_image: 'ghcr.io/arii/boomtick:${{ github.sha }}',
    });
    expect(action['continue-on-error']).toBeUndefined();
  });
  it('asserts generated artifacts and runs actual image entrypoint offline, with the real mount and bundle path', () => {
    const artifacts = steps.find((step: any) => step.name === 'Assert Composite Impact Artifacts');
    expect(artifacts.run).toContain('test -s artifacts/impact-analysis.json');
    expect(artifacts.run).toContain('jq -e');
    const smoke = steps.find((step: any) => step.name === 'Smoke Test Real Container Review Contracts Offline');
    expect(smoke.run).toContain('docker run --rm --network none');
    expect(smoke.run).toContain('-v "${{ github.workspace }}":/github/workspace');
    expect(smoke.run).toContain('ghcr.io/arii/boomtick:${{ github.sha }}');
    expect(smoke.run).toContain('node /github/workspace/scripts/smoke-review-offline.mjs /workspace/dist');
    expect(smoke.run).not.toContain('--entrypoint');
    expect(smoke.run).not.toContain('GEMINI_API_KEY');
    expect(smoke['continue-on-error']).toBeUndefined();
    expect(smoke.if).toBeUndefined();
  });
  it('retains separate real Deployment Impact provider input and required failure behavior', () => {
    const ci = yaml.parse(fs.readFileSync(path.join(root, '.github/workflows/ci.yml'), 'utf8'));
    const impact = ci.jobs['impact-analysis'];
    expect(impact.name).toBe('Deployment Impact Analysis');
    expect(impact['continue-on-error']).toBeUndefined();
    const action = impact.steps.find((step: any) => step.uses === './.github/actions/impact-analysis');
    expect(action.with.gemini_api_key).toBe('${{ secrets.GEMINI_API_KEY }}');
    expect(action['continue-on-error']).toBeUndefined();
  });
});
