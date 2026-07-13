import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { loadProjectConfig, DEFAULT_CONFIG } from '../../lib/projectConfig';

describe('loadProjectConfig', () => {
  let tempDir: string;
  let consoleWarnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'project-config-test-'));
    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  });

  afterEach(() => {
    fs.rmSync(tempDir, { recursive: true, force: true });
    if (consoleWarnSpy) {
      consoleWarnSpy.mockRestore();
    }
  });

  it('returns default config when file does not exist', () => {
    const config = loadProjectConfig(path.join(tempDir, 'non-existent.json'));
    expect(config).toEqual(DEFAULT_CONFIG);
  });

  it('parses valid JSON correctly', () => {
    const configPath = path.join(tempDir, 'project_config.json');
    const customConfig = {
      core_dirs: ['src/ui/'],
      monolithic_pr_threshold: 5,
      base_branch: 'develop',
      max_diff_chars: 50000,
      content_scopes: { docs: 'content/docs/' },
      ai_synthesis_model: 'gpt-4o'
    };
    fs.writeFileSync(configPath, JSON.stringify(customConfig));

    const config = loadProjectConfig(configPath);
    expect(config).toEqual(customConfig);
  });

  it('falls back to defaults for missing keys', () => {
    const configPath = path.join(tempDir, 'partial_config.json');
    const partialConfig = {
      base_branch: 'feat/new-thing'
    };
    fs.writeFileSync(configPath, JSON.stringify(partialConfig));

    const config = loadProjectConfig(configPath);
    expect(config.base_branch).toBe('feat/new-thing');
    expect(config.monolithic_pr_threshold).toBe(DEFAULT_CONFIG.monolithic_pr_threshold);
    expect(config.core_dirs).toEqual(DEFAULT_CONFIG.core_dirs);
  });

  it('handles malformed JSON by returning defaults', () => {
    const configPath = path.join(tempDir, 'malformed.json');
    fs.writeFileSync(configPath, 'invalid json {');

    const config = loadProjectConfig(configPath);
    expect(config).toEqual(DEFAULT_CONFIG);
    expect(consoleWarnSpy).toHaveBeenCalledWith(expect.stringContaining('⚠️  Failed to load project_config.json, using defaults.'), expect.any(Error));
  });

  it('validates types and falls back to defaults for invalid types', () => {
    const configPath = path.join(tempDir, 'invalid_types.json');
    const invalidTypeConfig = {
      monolithic_pr_threshold: { not: 'a-number' },
      core_dirs: 'not-an-array'
    };
    fs.writeFileSync(configPath, JSON.stringify(invalidTypeConfig));

    const config = loadProjectConfig(configPath);
    expect(config.monolithic_pr_threshold).toBe(DEFAULT_CONFIG.monolithic_pr_threshold);
    expect(config.core_dirs).toEqual(DEFAULT_CONFIG.core_dirs);
  });

  it('coerces strings to numbers where appropriate', () => {
    const configPath = path.join(tempDir, 'string_nums.json');
    const stringNumConfig = {
      monolithic_pr_threshold: '10',
      max_diff_chars: '60000'
    };
    fs.writeFileSync(configPath, JSON.stringify(stringNumConfig));

    const config = loadProjectConfig(configPath);
    expect(config.monolithic_pr_threshold).toBe(10);
    expect(config.max_diff_chars).toBe(60000);
  });
});
