import * as fs from 'fs';
import * as path from 'path';

export interface ProjectConfig {
  core_dirs: string[];
  monolithic_pr_threshold: number;
  base_branch: string;
  max_diff_chars: number;
  content_scopes: Record<string, string>;
  ai_synthesis_model: string;
}

export const DEFAULT_CONFIG: ProjectConfig = {
  core_dirs: ["src/layouts/", "src/components/"],
  monolithic_pr_threshold: 3,
  base_branch: "origin/main",
  max_diff_chars: 40000,
  content_scopes: {
    "resources": "content/resources/",
    "posts": "content/posts/",
    "blog": "content/blog/",
    "studies": "content/studies/"
  },
  ai_synthesis_model: "gpt-4o-mini"
};

/**
 * Loads project configuration from dev-tools/project_config.json.
 * Gracefully handles missing or malformed configuration files.
 */
export function loadProjectConfig(explicitPath?: string): ProjectConfig {
  try {
    const configPath = explicitPath || path.join(process.cwd(), 'project_config.json');
    if (!fs.existsSync(configPath)) return DEFAULT_CONFIG;

    const fileContent = fs.readFileSync(configPath, 'utf-8');
    const parsed: unknown = JSON.parse(fileContent);

    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return DEFAULT_CONFIG;
    }

    const raw = parsed as Record<string, unknown>;

    const getInt = (val: unknown, fallback: number): number => {
      if (typeof val === 'number') return val;
      if (typeof val === 'string') {
        const p = parseInt(val, 10);
        if (!isNaN(p)) return p;
      }
      return fallback;
    };

    const core_dirs = Array.isArray(raw.core_dirs)
      ? raw.core_dirs.map(String)
      : DEFAULT_CONFIG.core_dirs;

    const monolithic_pr_threshold = getInt(raw.monolithic_pr_threshold, DEFAULT_CONFIG.monolithic_pr_threshold);
    const base_branch = typeof raw.base_branch === 'string' ? raw.base_branch : DEFAULT_CONFIG.base_branch;
    const max_diff_chars = getInt(raw.max_diff_chars, DEFAULT_CONFIG.max_diff_chars);

    let content_scopes = DEFAULT_CONFIG.content_scopes;
    if (raw.content_scopes && typeof raw.content_scopes === 'object' && !Array.isArray(raw.content_scopes)) {
      content_scopes = Object.fromEntries(
        Object.entries(raw.content_scopes as Record<string, unknown>).map(([k, v]) => [String(k), String(v)])
      );
    }

    const ai_synthesis_model = typeof raw.ai_synthesis_model === 'string'
      ? raw.ai_synthesis_model
      : DEFAULT_CONFIG.ai_synthesis_model;

    return {
      core_dirs,
      monolithic_pr_threshold,
      base_branch,
      max_diff_chars,
      content_scopes,
      ai_synthesis_model
    };
  } catch (err) {
    console.warn('⚠️  Failed to load project_config.json, using defaults.', err);
    return DEFAULT_CONFIG;
  }
}

/**
 * Detects if the current directory appears to be a web project (e.g. Vite).
 */
export function isWebProject(): boolean {
  if (fs.existsSync(path.join(process.cwd(), 'vite.config.ts'))) return true;
  if (fs.existsSync(path.join(process.cwd(), 'vite.config.js'))) return true;
  if (fs.existsSync(path.join(process.cwd(), 'src', 'App.tsx'))) return true;

  try {
    const pkgPath = path.join(process.cwd(), 'package.json');
    if (fs.existsSync(pkgPath)) {
      const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf-8'));
      if (pkg.scripts && (pkg.scripts.build || pkg.scripts.dev)) {
        // Broadly check for vite dependency if scripts are generic
        if (pkg.dependencies?.vite || pkg.devDependencies?.vite) return true;
      }
    }
  } catch {
    // Ignore parsing errors
  }

  return false;
}
