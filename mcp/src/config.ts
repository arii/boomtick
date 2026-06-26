import dotenv from "dotenv";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

dotenv.config({
  path: path.resolve(__dirname, "../.env"),
  quiet: true
});

export const config = {
  githubToken: process.env.GITHUB_TOKEN,
  githubOwner: process.env.GITHUB_OWNER || "arii",
  githubRepo: process.env.GITHUB_REPO || "tech-dancer",
  repoPath: process.env.BOOMTICK_REPO_PATH || path.resolve(__dirname, "../../../../"),
  defaultBaseBranch: process.env.DEFAULT_BASE_BRANCH || "main",
  viteBasePath: process.env.VITE_BASE_PATH || "/tech-dancer/",
  ghPath: process.env.GH_PATH || "gh"
};
