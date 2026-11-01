import fs from "fs/promises";
import * as syncFs from "fs";
import path from "path";
import crypto from "crypto";
import { config } from "../config.js";
import { resolveRepoPath } from "./git.js";
import { runCommand, ShellResult } from "./shell.js";

export interface SessionVerification {
  testsPassed: boolean;
  errors?: string | null;
  exitCode?: number | null;
}

export interface SessionData {
  sessionId: string;
  worktreeId: string;
  worktreePath: string;
  brief: string;
  model?: string | null;
  repo?: string | null;
  state: "running" | "done" | "failed";
  status: "running" | "ready";
  startedAt: number;
  lastCheckpoint: string;
  changedFiles: string[];
  lastVerification?: SessionVerification | null;
  logs: string[];
}

export interface DispatchOptions {
  worktreeId: string;
  brief: string;
  model?: string | null;
  repo?: string | null;
}

export interface ContainmentCheckResult {
  allowed: boolean;
  canonicalWorktree: string;
  canonicalTarget: string;
}

export class SessionManager {
  private static instance: SessionManager;
  private memorySessions: Map<string, SessionData> = new Map();

  private constructor() {}

  public static getInstance(): SessionManager {
    if (!SessionManager.instance) {
      SessionManager.instance = new SessionManager();
    }
    return SessionManager.instance;
  }

  /**
   * Resets sessions in memory (useful for testing).
   */
  public reset(): void {
    this.memorySessions.clear();
  }

  /**
   * Resolves the root workspace repository directory.
   */
  public getRepoRoot(repo?: string | null): string {
    return resolveRepoPath({ repo });
  }

  /**
   * Resolves the canonical worktree directory from a worktreeId.
   * Worktrees are stored under `<repoRoot>/.worktrees/<worktreeId>` or directly if already an existing path.
   */
  public resolveWorktreePath(worktreeId: string, repo?: string | null): string {
    const repoRoot = this.getRepoRoot(repo);
    // If worktreeId is absolute or relative path that exists
    if (path.isAbsolute(worktreeId) && syncFs.existsSync(worktreeId)) {
      return path.resolve(worktreeId);
    }

    const defaultWorktreeDir = path.resolve(repoRoot, ".worktrees", worktreeId);
    return defaultWorktreeDir;
  }

  /**
   * Checks whether targetPath is contained strictly inside worktreePath.
   * Throws an error if escaping worktree root (path traversal or symlinks).
   */
  public assertContainedPath(worktreePath: string, targetPath: string): string {
    const canonicalWorktree = syncFs.existsSync(worktreePath)
      ? syncFs.realpathSync(worktreePath)
      : path.resolve(worktreePath);

    const resolvedTarget = path.resolve(canonicalWorktree, targetPath);

    // If target exists, verify realpath to guard against symlink escapes
    if (syncFs.existsSync(resolvedTarget)) {
      const realTarget = syncFs.realpathSync(resolvedTarget);
      if (realTarget !== canonicalWorktree && !realTarget.startsWith(canonicalWorktree + path.sep)) {
        throw new Error(
          `Containment error: Target path '${targetPath}' escapes worktree root '${worktreePath}'`
        );
      }
      return realTarget;
    }

    // If target doesn't exist yet, check lexical containment against canonicalWorktree
    if (resolvedTarget !== canonicalWorktree && !resolvedTarget.startsWith(canonicalWorktree + path.sep)) {
      throw new Error(
        `Containment error: Target path '${targetPath}' escapes worktree root '${worktreePath}'`
      );
    }

    // Also check ancestor dirs of resolvedTarget to ensure no symlinks escape
    let cur = path.dirname(resolvedTarget);
    while (cur.length >= canonicalWorktree.length) {
      if (syncFs.existsSync(cur)) {
        const realCur = syncFs.realpathSync(cur);
        if (realCur !== canonicalWorktree && !realCur.startsWith(canonicalWorktree + path.sep)) {
          throw new Error(
            `Containment error: Symlink parent '${cur}' escapes worktree root '${worktreePath}'`
          );
        }
        break;
      }
      const parent = path.dirname(cur);
      if (parent === cur) break;
      cur = parent;
    }

    return resolvedTarget;
  }

  /**
   * Loads the isolated task context:
   * 1. repair-agent prompt (mcp/src/agents/repair-agent.prompt.md)
   * 2. Local worktree contract (.agents/AGENT_CONTRACT.md)
   * 3. Explicit task brief
   * Note: repo_read_agent_context is NOT auto-loaded.
   */
  public async loadSessionContext(
    worktreePath: string,
    brief: string
  ): Promise<{ systemPrompt: string; localContract: string; brief: string }> {
    let systemPrompt = "";
    try {
      const promptPath = path.resolve(config.repoPath || process.cwd(), "mcp/src/agents/repair-agent.prompt.md");
      if (syncFs.existsSync(promptPath)) {
        systemPrompt = await fs.readFile(promptPath, "utf-8");
      }
    } catch {
      // fallback
    }

    let localContract = "";
    try {
      const contractPath = path.resolve(worktreePath, ".agents", "AGENT_CONTRACT.md");
      if (syncFs.existsSync(contractPath)) {
        localContract = await fs.readFile(contractPath, "utf-8");
      }
    } catch {
      // fallback
    }

    return {
      systemPrompt,
      localContract,
      brief,
    };
  }

  /**
   * Extracts deterministic verification commands (testCommand, lintCommand) strictly from the agent contract.
   * Never relies on caller or hallucinated commands.
   */
  public extractContractCommands(contractContent: string): {
    testCommand: string;
    lintCommand?: string;
    commands: string[];
  } {
    let testCommand = "pnpm test";
    let lintCommand: string | undefined = undefined;

    // 1. Look for testCommand / lintCommand in yaml / json / markdown fields
    const testMatch = contractContent.match(/testCommand:\s*["']?([^"'\r\n]+)["']?/i) ||
      contractContent.match(/test_command:\s*["']?([^"'\r\n]+)["']?/i) ||
      contractContent.match(/`([^`]*(?:test|pytest|vitest|npm test|pnpm test)[^`]*)`/i);

    if (testMatch && testMatch[1]) {
      testCommand = testMatch[1].trim();
    }

    const lintMatch = contractContent.match(/lintCommand:\s*["']?([^"'\r\n]+)["']?/i) ||
      contractContent.match(/lint_command:\s*["']?([^"'\r\n]+)["']?/i) ||
      contractContent.match(/`([^`]*(?:lint|eslint|oxlint)[^`]*)`/i);

    if (lintMatch && lintMatch[1]) {
      lintCommand = lintMatch[1].trim();
    }

    const commands: string[] = [];
    if (lintCommand) {
      commands.push(lintCommand);
    }
    if (testCommand) {
      commands.push(testCommand);
    }

    return {
      testCommand,
      lintCommand,
      commands,
    };
  }

  /**
   * Saves session data to disk (`.worktrees/<worktreeId>/session.json`).
   */
  public async persistSession(session: SessionData): Promise<void> {
    try {
      if (!syncFs.existsSync(session.worktreePath)) {
        await fs.mkdir(session.worktreePath, { recursive: true });
      }
      const sessionFilePath = path.join(session.worktreePath, "session.json");
      await fs.writeFile(sessionFilePath, JSON.stringify(session, null, 2), "utf-8");
    } catch (err) {
      console.error(`Failed to persist session ${session.sessionId}:`, err);
    }
  }

  /**
   * Loads session from disk if not present in memory.
   */
  public async loadSession(sessionId: string): Promise<SessionData | null> {
    if (this.memorySessions.has(sessionId)) {
      return this.memorySessions.get(sessionId)!;
    }

    // Try finding in active worktrees directory
    const repoRoot = this.getRepoRoot();
    const worktreesDir = path.resolve(repoRoot, ".worktrees");
    if (syncFs.existsSync(worktreesDir)) {
      const entries = await fs.readdir(worktreesDir);
      for (const entry of entries) {
        const candidateSessionFile = path.join(worktreesDir, entry, "session.json");
        if (syncFs.existsSync(candidateSessionFile)) {
          try {
            const raw = await fs.readFile(candidateSessionFile, "utf-8");
            const data = JSON.parse(raw) as SessionData;
            if (data.sessionId === sessionId) {
              this.memorySessions.set(sessionId, data);
              return data;
            }
          } catch {
            // ignore corrupted files
          }
        }
      }
    }

    return null;
  }

  /**
   * Spawns / dispatches an agent session scoped to a worktree.
   */
  public async dispatch(options: DispatchOptions): Promise<SessionData> {
    const worktreePath = this.resolveWorktreePath(options.worktreeId, options.repo);

    if (!syncFs.existsSync(worktreePath)) {
      throw new Error(`Worktree not found for worktreeId '${options.worktreeId}' at path '${worktreePath}'`);
    }

    const sessionId = `session-${crypto.randomBytes(6).toString("hex")}`;
    const startedAt = Date.now();

    const session: SessionData = {
      sessionId,
      worktreeId: options.worktreeId,
      worktreePath,
      brief: options.brief,
      model: options.model || null,
      repo: options.repo || null,
      state: "running",
      status: "running",
      startedAt,
      lastCheckpoint: "worktree_setup",
      changedFiles: [],
      lastVerification: null,
      logs: [
        `[${new Date(startedAt).toISOString()}] Session ${sessionId} dispatched for worktree ${options.worktreeId}`,
        `[${new Date(startedAt).toISOString()}] Model: ${options.model || "default"} | Jail CWD: ${worktreePath}`,
        `[${new Date(startedAt).toISOString()}] State: running | Checkpoint: worktree_setup`,
      ],
    };

    // Isolated task context verification
    const context = await this.loadSessionContext(worktreePath, options.brief);
    session.logs.push(`[${new Date().toISOString()}] Context loaded: zero ambient context (repair-agent prompt + local contract)`);

    this.memorySessions.set(sessionId, session);
    await this.persistSession(session);

    return session;
  }

  /**
   * Appends logs to session transcript and updates session file.
   */
  public async appendLogs(sessionId: string, newLogs: string[]): Promise<void> {
    const session = await this.loadSession(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }

    session.logs.push(...newLogs);
    await this.persistSession(session);
  }

  /**
   * Updates session checkpoint and status.
   */
  public async updateCheckpoint(
    sessionId: string,
    checkpoint: string,
    state?: "running" | "done" | "failed"
  ): Promise<void> {
    const session = await this.loadSession(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }

    session.lastCheckpoint = checkpoint;
    if (state) {
      session.state = state;
      session.status = state === "running" ? "running" : "ready";
    }
    session.logs.push(`[${new Date().toISOString()}] Checkpoint updated: ${checkpoint}${state ? ` (state: ${state})` : ""}`);

    // Update changed files via git status inside worktree
    try {
      const statusRes = await runCommand("git", ["status", "--porcelain"], { cwd: session.worktreePath });
      session.changedFiles = statusRes.stdout
        .split("\n")
        .map((l) => (l.endsWith("\r") ? l.slice(0, -1) : l))
        .filter((l) => l.trim().length > 0)
        .map((l) => {
          const match = l.match(/^..\s+(.*)$/);
          if (!match) return l.slice(3).trim();
          let file = match[1].trim();
          if (file.includes(" -> ")) {
            file = file.split(" -> ").pop()!.trim();
          }
          if (file.startsWith('"') && file.endsWith('"')) {
            file = file.slice(1, -1);
          }
          return file;
        })
        .filter(Boolean);
    } catch {
      // ignore git status errors
    }

    await this.persistSession(session);
  }

  /**
   * Runs verification extracted strictly from the worktree's contract.
   */
  public async runVerification(sessionId: string): Promise<SessionVerification> {
    const session = await this.loadSession(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }

    const context = await this.loadSessionContext(session.worktreePath, session.brief);
    const contractCmds = this.extractContractCommands(context.localContract);

    session.logs.push(
      `[${new Date().toISOString()}] Running verification extracted from contract: ${contractCmds.commands.join(", ")}`
    );

    let testsPassed = true;
    let errors: string | undefined = undefined;
    let lastExitCode: number | null = 0;

    for (const fullCmd of contractCmds.commands) {
      const tokens: string[] = fullCmd.split(/\s+/).filter(Boolean);
      const [cmd, ...args] = tokens;
      try {
        const res: ShellResult = await runCommand(cmd, args, { cwd: session.worktreePath });
        session.logs.push(`[CMD] ${fullCmd} -> exit code ${res.exitCode}`);
        if (res.exitCode !== 0) {
          testsPassed = false;
          errors = res.stderr || res.stdout || `Command failed with code ${res.exitCode}`;
          lastExitCode = res.exitCode;
          break;
        }
      } catch (err: any) {
        testsPassed = false;
        errors = err.message;
        lastExitCode = 1;
        break;
      }
    }

    const verification: SessionVerification = {
      testsPassed,
      errors: errors || null,
      exitCode: lastExitCode ?? null,
    };

    session.lastVerification = verification;
    await this.updateCheckpoint(sessionId, "test_verification", testsPassed ? "done" : "failed");

    return verification;
  }

  /**
   * Validates and executes patch commit gated by files modified during the session.
   */
  public async commitPatch(
    sessionId: string,
    message: string,
    allowedFiles: string[]
  ): Promise<{ success: boolean; commitSha: string; changedFiles: string[] }> {
    const session = await this.loadSession(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }

    // Refresh changed files via git status
    const statusRes = await runCommand("git", ["status", "--porcelain"], { cwd: session.worktreePath });
    const currentChangedFiles = statusRes.stdout
      .split("\n")
      .map((l) => (l.endsWith("\r") ? l.slice(0, -1) : l))
      .filter((l) => l.trim().length > 0)
      .map((l) => {
        const match = l.match(/^..\s+(.*)$/);
        if (!match) return l.slice(3).trim();
        let file = match[1].trim();
        if (file.includes(" -> ")) {
          file = file.split(" -> ").pop()!.trim();
        }
        if (file.startsWith('"') && file.endsWith('"')) {
          file = file.slice(1, -1);
        }
        return file;
      })
      .filter((f) => f && f !== "session.json");

    session.changedFiles = currentChangedFiles;

    // Check if committing files not modified in the session
    const unauthorizedFiles = allowedFiles.filter((f) => !currentChangedFiles.includes(f));
    if (unauthorizedFiles.length > 0) {
      throw new Error(
        `commit_patch failed: cannot commit files not modified in the session: ${unauthorizedFiles.join(", ")}`
      );
    }

    const forbiddenFiles = currentChangedFiles.filter((f) => !allowedFiles.includes(f));
    if (forbiddenFiles.length > 0) {
      throw new Error(
        `commit_patch failed: working tree contains unapproved modified files: ${forbiddenFiles.join(", ")}`
      );
    }

    if (currentChangedFiles.length === 0) {
      throw new Error("commit_patch failed: No changes to commit");
    }

    // Stage and commit
    await runCommand("git", ["add", "--", ...currentChangedFiles], { cwd: session.worktreePath });
    const commitRes = await runCommand("git", ["commit", "-m", message], { cwd: session.worktreePath });
    if (commitRes.exitCode !== 0) {
      throw new Error(`commit_patch git commit failed: ${commitRes.stderr}`);
    }

    const revParse = await runCommand("git", ["rev-parse", "HEAD"], { cwd: session.worktreePath });
    const commitSha = revParse.stdout.trim();

    session.logs.push(`[${new Date().toISOString()}] Committed patch: ${commitSha} (${currentChangedFiles.join(", ")})`);
    await this.updateCheckpoint(sessionId, "checkpoint", "done");

    return {
      success: true,
      commitSha,
      changedFiles: currentChangedFiles,
    };
  }

  /**
   * Retrieves session status.
   */
  public async getStatus(sessionId: string): Promise<SessionData> {
    const session = await this.loadSession(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }

    // Refresh changedFiles from git status
    try {
      const statusRes = await runCommand("git", ["status", "--porcelain"], { cwd: session.worktreePath });
      session.changedFiles = statusRes.stdout
        .split("\n")
        .map((l) => (l.endsWith("\r") ? l.slice(0, -1) : l))
        .filter((l) => l.trim().length > 0)
        .map((l) => {
          const match = l.match(/^..\s+(.*)$/);
          if (!match) return l.slice(3).trim();
          let file = match[1].trim();
          if (file.includes(" -> ")) {
            file = file.split(" -> ").pop()!.trim();
          }
          if (file.startsWith('"') && file.endsWith('"')) {
            file = file.slice(1, -1);
          }
          return file;
        })
        .filter(Boolean);
    } catch {
      // ignore
    }

    return session;
  }

  /**
   * Retrieves tail of session logs.
   */
  public async getLogs(
    sessionId: string,
    tail: number = 100
  ): Promise<{ sessionId: string; logs: string[]; totalLines: number }> {
    const session = await this.loadSession(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }

    const totalLines = session.logs.length;
    const tailCount = Math.max(0, tail);
    const returnedLogs = session.logs.slice(-tailCount);

    return {
      sessionId,
      logs: returnedLogs,
      totalLines,
    };
  }
}
