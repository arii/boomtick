import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export function findRepoRoot(startDir?: string): string {
  let current = startDir || process.cwd();
  while (current !== path.parse(current).root) {
    if (
      fs.existsSync(path.join(current, "project_config.json")) ||
      fs.existsSync(path.join(current, "workspace.json")) ||
      fs.existsSync(path.join(current, ".git"))
    ) {
      return current;
    }
    current = path.dirname(current);
  }

  if (process.env.BOOMTICK_REPO_PATH) {
    return process.env.BOOMTICK_REPO_PATH;
  }

  current = __dirname;
  while (current !== path.parse(current).root) {
    if (
      fs.existsSync(path.join(current, "project_config.json")) ||
      fs.existsSync(path.join(current, "workspace.json")) ||
      fs.existsSync(path.join(current, ".git"))
    ) {
      return current;
    }
    current = path.dirname(current);
  }
  return path.resolve(__dirname, "../../../../");
}

interface PerRepoConfigSnapshot {
  root: string;
  githubRepo?: string;
}

let perRepoConfigSnapshot: PerRepoConfigSnapshot | null = null;

/**
 * Read github_repo from the project_config.json governing startDir — the
 * caller's own repo declaration. This is the most specific repo signal and
 * outranks machine-global configuration (e.g. `td config view`), which may
 * point at an unrelated repo.
 */
export function readPerRepoGithubRepo(startDir?: string): string | undefined {
  const root = findRepoRoot(startDir);
  if (perRepoConfigSnapshot?.root === root) {
    return perRepoConfigSnapshot.githubRepo;
  }
  let githubRepo: string | undefined;
  try {
    const parsed = JSON.parse(fs.readFileSync(path.join(root, "project_config.json"), "utf-8"));
    if (typeof parsed?.github_repo === "string" && parsed.github_repo.includes("/")) {
      githubRepo = parsed.github_repo;
    }
  } catch {
    // No per-repo declaration → undefined; callers fall through to other signals.
  }
  perRepoConfigSnapshot = { root, githubRepo };
  return githubRepo;
}
