import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getGeminiPricing } from '../../lib/geminiModelPicker';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '../..');
const DATA_PATH = path.join(REPO_ROOT, 'lib/gemini-models.json');
const PICKER_PATH = path.join(REPO_ROOT, 'lib/geminiModelPicker.ts');

interface CatalogModel {
  id: string;
  tier: string;
  inputCostPerM: number;
  outputCostPerM: number;
  reviewAfter: string | null;
  deprecatedAfter: string | null;
}

interface Catalog {
  models: CatalogModel[];
  defaultPricing: { inputCostPerM: number; outputCostPerM: number };
  deprecated: { id: string }[];
}

function readCatalog(): Catalog {
  return JSON.parse(fs.readFileSync(DATA_PATH, 'utf8')) as Catalog;
}

describe('geminiModelPicker file-driven catalog (issue #1227)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('resolves pricing from lib/gemini-models.json entries', () => {
    const catalog = readCatalog();
    expect(catalog.models.length).toBeGreaterThan(0);
    for (const model of catalog.models) {
      expect(getGeminiPricing(model.id)).toEqual({
        inputCostPerM: model.inputCostPerM,
        outputCostPerM: model.outputCostPerM,
      });
    }
  });

  it('falls back to the data file defaultPricing for unknown ids', () => {
    const catalog = readCatalog();
    expect(getGeminiPricing('gemini-no-such-model-xyz')).toEqual(catalog.defaultPricing);
  });

  it('carries no hardcoded model ids in picker logic', () => {
    const source = fs.readFileSync(PICKER_PATH, 'utf8');
    expect(source).toContain('gemini-models.json');
    expect(source).not.toContain('gemini-1.5');
    expect(source).not.toContain('gemini-2.0');
  });

  it('warns visibly when a catalog entry passes its review date', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2030-01-01T00:00:00Z'));
    vi.resetModules();
    await import('../../lib/geminiModelPicker');
    const warned = warnSpy.mock.calls.some((args) => String(args[0]).includes('gemini-3.5-flash'));
    expect(warned).toBe(true);
  });
});
