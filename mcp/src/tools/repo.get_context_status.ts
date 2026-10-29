import { z } from "zod";
import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";
import { GetContextStatusInputSchema } from "./contract.js";
import { resolveTargetRepoPath } from "./repo.read_agent_context.js";

export { GetContextStatusInputSchema };

export async function getContextStatusHandler(args: z.infer<typeof GetContextStatusInputSchema>) {
  const targetPath = await resolveTargetRepoPath(args);
  const contextFile = path.join(targetPath, ".agent-context.json");

  if (!fs.existsSync(contextFile)) {
    return {
      warm: false,
      lastWarmedAt: null,
      path: contextFile,
      staleFiles: [".agent-context.json missing"],
    };
  }

  let lastWarmedAt: string | null = null;
  let contextMtime = 0;
  try {
    const stats = fs.statSync(contextFile);
    contextMtime = stats.mtimeMs;
    lastWarmedAt = stats.mtime.toISOString();
  } catch {
    // stat failed
  }

  let isStale = false;
  const staleFiles: string[] = [];

  // Check git commit timestamp of context file vs HEAD commit timestamp
  try {
    const gitRes = execSync("git log -1 --format=%ct -- .agent-context.json", {
      cwd: targetPath,
      encoding: "utf-8",
      stdio: ["pipe", "pipe", "ignore"],
    }).trim();
    const contextCommitTs = parseInt(gitRes || "0", 10);

    const headRes = execSync("git log -1 --format=%ct HEAD", {
      cwd: targetPath,
      encoding: "utf-8",
      stdio: ["pipe", "pipe", "ignore"],
    }).trim();
    const headTs = parseInt(headRes || "0", 10);

    if (headTs > contextCommitTs) {
      isStale = true;
      staleFiles.push("HEAD commit is newer than .agent-context.json commit");
    }
  } catch {
    // Git check fallback
  }

  // Check if any tracked modified/uncommitted files or major config files are newer than .agent-context.json mtime
  const keyFiles = ["package.json", "project_config.json", "cli/dev_tools/cli-schema.json"];
  for (const keyFile of keyFiles) {
    const fullPath = path.join(targetPath, keyFile);
    if (fs.existsSync(fullPath)) {
      try {
        const fileStats = fs.statSync(fullPath);
        if (fileStats.mtimeMs > contextMtime) {
          isStale = true;
          if (!staleFiles.includes(keyFile)) {
            staleFiles.push(keyFile);
          }
        }
      } catch {
        // ignore
      }
    }
  }

  return {
    warm: !isStale,
    lastWarmedAt,
    path: contextFile,
    staleFiles,
  };
}
