import fs from 'fs';
import os from 'os';
import path from 'path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { resolveAffectedUrls } from '../../lib/impact-analysis-utils';
import { IMPACT_CONFIG } from '../../scripts/impact-analysis.config';

let dir: string;
const original = IMPACT_CONFIG.URL_INVENTORY_FILE;
beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'impact-inventory-'));
  IMPACT_CONFIG.URL_INVENTORY_FILE = path.join(dir, 'urls.json');
  fs.writeFileSync(IMPACT_CONFIG.URL_INVENTORY_FILE, JSON.stringify(['/', '/about', '/blog/one', '/blog/two', '/research/one']));
});
afterEach(() => {
  IMPACT_CONFIG.URL_INVENTORY_FILE = original;
  fs.rmSync(dir, { recursive: true, force: true });
});
const resolve = (file: string, route: string) => resolveAffectedUrls([file], [file], { [file]: route }, []);

describe('authoritative impact URL inventory', () => {
  it('selects a static page URL', () => {
    expect(resolve('src/pages/About.tsx', '/about')).toEqual(['/about']);
  });
  it('selects only concrete URLs matching a dynamic route', () => {
    expect(resolve('src/pages/BlogPost.tsx', '/blog/:slug')).toEqual(['/blog/one', '/blog/two']);
  });
  it('excludes routes absent from the inventory', () => {
    expect(resolve('src/pages/Missing.tsx', '/missing')).toEqual([]);
  });
  it('distinguishes missing inventory from a genuine zero-route result', () => {
    fs.writeFileSync(IMPACT_CONFIG.URL_INVENTORY_FILE, '[]');
    expect(resolve('src/pages/About.tsx', '/about')).toEqual([]);
    fs.unlinkSync(IMPACT_CONFIG.URL_INVENTORY_FILE);
    expect(() => resolve('src/pages/About.tsx', '/about')).toThrow('No URL inventory');
  });
  it('rejects invalid or non-concrete inventory entries', () => {
    fs.writeFileSync(IMPACT_CONFIG.URL_INVENTORY_FILE, '["/blog/:slug"]');
    expect(() => resolve('src/pages/About.tsx', '/about')).toThrow('No URL inventory');
  });
  it('does not require inventory for changes with no page impact', () => {
    fs.unlinkSync(IMPACT_CONFIG.URL_INVENTORY_FILE);
    expect(resolveAffectedUrls(['cli/tool.py'], ['cli/tool.py'], {}, [])).toEqual([]);
  });
});
