import { execSync } from "child_process";

export function getGithubToken(): string | undefined {
  if (process.env.GITHUB_TOKEN) {
    return process.env.GITHUB_TOKEN;
  }
  try {
    const token = execSync("gh auth token", { encoding: "utf-8", stdio: ["ignore", "pipe", "ignore"] }).trim();
    if (token) {
      return token;
    }
  } catch {
    /* ignore to allow fallback */
  }
  return undefined;
}
