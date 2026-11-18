import { execSync } from "child_process";

const repoCache = new Map<string, string>();

export function resolveRepo(explicitRepo?: string | null, cwd?: string): string {
  if (explicitRepo && explicitRepo.trim().length > 0) {
    return explicitRepo.trim();
  }

  const targetCwd = cwd || process.cwd();
  if (repoCache.has(targetCwd)) {
    return repoCache.get(targetCwd)!;
  }

  let gitFailure: string;
  try {
    const url = execSync("git remote get-url origin", {
      cwd: targetCwd,
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();

    const match = url.match(/[:/]([^/]+\/[^/.]+)(\.git)?$/);
    if (match) {
      repoCache.set(targetCwd, match[1]);
      return match[1];
    }
    gitFailure = `could not parse repo from git remote url ${JSON.stringify(url)}`;
  } catch (e) {
    gitFailure = e instanceof Error ? e.message : String(e);
  }

  throw new Error(
    `Cannot resolve repo: no explicit repo was given and git remote detection failed for cwd ${JSON.stringify(targetCwd)} (${gitFailure}). Run inside a git checkout with an 'origin' remote, or pass an explicit repo (e.g. "owner/name").`
  );
}
