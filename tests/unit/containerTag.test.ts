import { describe, expect, it } from 'vitest';

const resolveContainerImage = (repo: string, sha?: string, tagOverride?: string): string => {
  if (tagOverride) {
    return `${repo}:${tagOverride}`;
  }
  if (sha) {
    return `${repo}:${sha}`;
  }
  return `${repo}:latest`;
};

describe('resolveContainerImage', () => {
  it('resolves immutable tag using commit SHA', () => {
    const image = resolveContainerImage('ghcr.io/arii/boomtick', 'a1b2c3d4e5f6');
    expect(image).toBe('ghcr.io/arii/boomtick:a1b2c3d4e5f6');
  });

  it('respects explicit tag override', () => {
    const image = resolveContainerImage('ghcr.io/arii/boomtick', 'a1b2c3d4e5f6', 'v1.2.0');
    expect(image).toBe('ghcr.io/arii/boomtick:v1.2.0');
  });

  it('defaults to latest only when no SHA or override exists', () => {
    const image = resolveContainerImage('ghcr.io/arii/boomtick');
    expect(image).toBe('ghcr.io/arii/boomtick:latest');
  });
});
