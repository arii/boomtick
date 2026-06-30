import dotenv from "dotenv";
import path from "path";
import { fileURLToPath } from "url";
import { execSync } from "child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

dotenv.config({
  path: path.resolve(__dirname, "../.env"),
  quiet: true
});

function getGithubToken(): string | undefined {
  if (process.env.GITHUB_TOKEN) {
    return process.env.GITHUB_TOKEN;
  }
  try {
    const token = execSync("gh auth token", { encoding: "utf-8", stdio: ["ignore", "pipe", "ignore"] }).trim();
    if (token) {
      return token;
    }
  } catch (e) {}
  return undefined;
}

export const config = {
  githubToken: getGithubToken(),
  githubOwner: process.env.GITHUB_OWNER || "arii",
  githubRepo: process.env.GITHUB_REPO || "tech-dancer",
  repoPath: process.env.BOOMTICK_REPO_PATH || path.resolve(__dirname, "../../../../"),
  defaultBaseBranch: process.env.DEFAULT_BASE_BRANCH || "main",
  viteBasePath: process.env.VITE_BASE_PATH || "/tech-dancer/",
  ghPath: process.env.GH_PATH || "gh"
};

