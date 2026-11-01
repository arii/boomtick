import { describe, expect, it, afterEach } from "vitest";
import path from "path";
import * as fs from "fs";
import * as os from "os";
import { readAgentContractHandler, parseAgentContractContent } from "./repo.read_agent_contract.js";

describe("repo.read_agent_contract Tool Handler", () => {
  const tempDirs: string[] = [];

  function createTempRepo(): string {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "agent-contract-test-"));
    tempDirs.push(tmpDir);
    fs.mkdirSync(path.join(tmpDir, ".agents"), { recursive: true });
    return tmpDir;
  }

  afterEach(() => {
    for (const dir of tempDirs) {
      try {
        fs.rmSync(dir, { recursive: true, force: true });
      } catch {
        // Ignore cleanup failure
      }
    }
    tempDirs.length = 0;
  });

  it("should read agent contract from current workspace by default", async () => {
    const res = await readAgentContractHandler({});
    expect(res.status).toBe("success");
    expect(res.content).toContain("# Agent Contract");
    expect(res.path).toContain("AGENT_CONTRACT.md");
    expect(res.config).toBeDefined();
    expect(res.config.baseBranch).toBe("main");
    expect(res.config.sharedDeps).toBe("symlink");
    expect(res.config.worktreeTtlDays).toBe(7);
  });

  it("should accept repoPath argument", async () => {
    const rootPath = path.resolve(process.cwd(), "..");
    const res = await readAgentContractHandler({ repoPath: rootPath });
    expect(res.status).toBe("success");
    expect(res.content).toBeDefined();
    expect(res.path).toContain("AGENT_CONTRACT.md");
  });

  it("should parse YAML front-matter and strip it from markdown content", async () => {
    const repoDir = createTempRepo();
    const contractPath = path.join(repoDir, ".agents", "AGENT_CONTRACT.md");
    const rawContent = `---
baseBranch: develop
setupCommand: pnpm install --frozen-lockfile
testCommand: pnpm test
lintCommand: pnpm lint
buildCommand: pnpm build
sharedDeps: symlink
sparsePaths:
  - src
  - package.json
worktreeTtlDays: 14
---
# Custom Agent Contract

Content goes here.
`;
    fs.writeFileSync(contractPath, rawContent, "utf-8");

    const res = await readAgentContractHandler({ path: repoDir });
    expect(res.status).toBe("success");
    expect(res.path).toBe(contractPath);
    expect(res.content).toBe("# Custom Agent Contract\n\nContent goes here.\n");
    expect(res.config).toEqual({
      baseBranch: "develop",
      setupCommand: "pnpm install --frozen-lockfile",
      testCommand: "pnpm test",
      lintCommand: "pnpm lint",
      buildCommand: "pnpm build",
      sharedDeps: "symlink",
      sparsePaths: ["src", "package.json"],
      worktreeTtlDays: 14,
    });
  });

  it("should fallback to .agents/agent-config.json when front-matter is absent", async () => {
    const repoDir = createTempRepo();
    const contractPath = path.join(repoDir, ".agents", "AGENT_CONTRACT.md");
    const jsonPath = path.join(repoDir, ".agents", "agent-config.json");

    fs.writeFileSync(contractPath, "# Markdown Contract without frontmatter\n", "utf-8");
    fs.writeFileSync(
      jsonPath,
      JSON.stringify({
        baseBranch: "staging",
        setupCommand: "npm ci",
        testCommand: "npm test",
        sharedDeps: "install",
      }),
      "utf-8"
    );

    const res = await readAgentContractHandler({ path: repoDir });
    expect(res.status).toBe("success");
    expect(res.content).toBe("# Markdown Contract without frontmatter\n");
    expect(res.config.baseBranch).toBe("staging");
    expect(res.config.setupCommand).toBe("npm ci");
    expect(res.config.testCommand).toBe("npm test");
    expect(res.config.sharedDeps).toBe("install");
    expect(res.config.worktreeTtlDays).toBe(7); // default value
  });

  it("should apply defaults when neither front-matter nor json config has custom fields", async () => {
    const repoDir = createTempRepo();
    const contractPath = path.join(repoDir, ".agents", "AGENT_CONTRACT.md");
    fs.writeFileSync(contractPath, "# Just Markdown\n", "utf-8");

    const res = await readAgentContractHandler({ path: repoDir });
    expect(res.status).toBe("success");
    expect(res.content).toBe("# Just Markdown\n");
    expect(res.config.baseBranch).toBe("main");
    expect(res.config.sharedDeps).toBe("symlink");
    expect(res.config.worktreeTtlDays).toBe(7);
    expect(res.config.setupCommand).toBeNull();
  });

  it("should handle corrupted front-matter gracefully without crashing", () => {
    const repoDir = createTempRepo();
    const rawContent = `---
[invalid yaml syntax:
---
# Contract Title
`;
    const { content, config } = parseAgentContractContent(rawContent, repoDir);
    expect(content).toBe("# Contract Title\n");
    expect(config.baseBranch).toBe("main");
  });
});
