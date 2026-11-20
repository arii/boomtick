import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import yaml from 'yaml';

const lock = yaml.parse(readFileSync(path.join(__dirname, '../../pnpm-lock.yaml'), 'utf8'));

// Regression floors from the reviewed November 2026 advisory triage.
// Package presence is not evidence that an advisory is reachable.
describe('reviewed dependency security floors', () => {
  const floors = [
    ['@modelcontextprotocol/sdk', [1, 32, 2]],
    ['zod', [4, 6, 7]],
    ['proxy-addr', [2, 0, 8]],
    ['shell-quote', [1, 11, 0]],
  ] as const;

  for (const [name, minimum] of floors) {
    it(`keeps every locked ${name} resolution above the reviewed floor`, () => {
      const versions = Object.keys(lock.packages).filter(key => key.startsWith(`${name}@`));
      expect(versions.length).toBeGreaterThan(0);
      for (const key of versions) {
        const version = key.slice(name.length + 1);
        expect(version).toMatch(/^\d+\.\d+\.\d+$/);
        const actual = version.split('.').map(Number);
        const firstDifference = minimum.findIndex((value, index) => actual[index] !== value);
        expect(firstDifference === -1 || actual[firstDifference] > minimum[firstDifference]).toBe(true);
      }
    });
  }
});
