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
