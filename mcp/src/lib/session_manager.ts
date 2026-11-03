import fs from "fs/promises";
import * as syncFs from "fs";
import path from "path";
import crypto from "crypto";
import { spawn } from "child_process";
import { config } from "../config.js";
import { resolveRepoPath, removeWorktree } from "./git.js";
import { runCommand } from "./shell.js";

const MAX_SESSION_LOG_LINES = 2000;

export type SessionState = "running" | "done" | "failed" | "abandoned";

export interface LastVerification {
  testsPassed: boolean;
  errors?: string | null;
  exitCode?: number | null;
  output?: string;
}

export type SessionVerification = LastVerification;

export interface AgentSession {
  sessionId: string;
  worktreeId: string;
  worktreePath: string;
  branch: string;
  baseBranch: string;
  repo?: string | null;
  brief: string;
  model?: string | null;
  state: SessionState;
  status?: "running" | "ready";
  startedAt?: number;
  createdAt: number;
  updatedAt: number;
  lastCheckpoint?: string;
  changedFiles?: string[];
  retries: number;
  maxRetries: number;
  transcript: string[];
  logs: string[];
  lastVerification?: LastVerification | null;
  pullRequestUrl?: string;
}

export type SessionData = AgentSession;

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
  private sessions: Map<string, AgentSession> = new Map();
  private locks: Map<string, Promise<void>> = new Map();

  private constructor() {}

  public static getInstance(): SessionManager {
    if (!SessionManager.instance) {
      SessionManager.instance = new SessionManager();
    }
    return SessionManager.instance;
  }

  /**
   * Resets singleton instance (useful for testing).
   */
  public static resetInstance(): void {
    SessionManager.instance = new SessionManager();
  }

  /**
   * Resets sessions in memory (useful for testing).
   */
  public reset(): void {
    this.sessions.clear();
    this.locks.clear();
  }

  /**
   * Acquire an asynchronous mutex lock for a specific sessionId to prevent race conditions.
   * Returns a release callback.
   */
  public async acquireLock(sessionId: string): Promise<() => void> {
    while (this.locks.has(sessionId)) {
      await this.locks.get(sessionId);
    }

    let releaseLock: () => void = () => {};
    const lockPromise = new Promise<void>((resolve) => {
      releaseLock = resolve;
    });

    this.locks.set(sessionId, lockPromise);

    return () => {
      this.locks.delete(sessionId);
      releaseLock();
    };
  }

  public registerSession(session: AgentSession): void {
    this.sessions.set(session.sessionId, session);
  }

  public getSession(sessionId: string): AgentSession {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Session not found: ${sessionId}`);
    }
    return session;
  }

  public hasSession(sessionId: string): boolean {
    return this.sessions.has(sessionId);
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
    const worktreesRoot = path.resolve(repoRoot, ".worktrees");

    if (!path.isAbsolute(worktreeId)) {
      return path.resolve(worktreesRoot, path.basename(worktreeId));
    }

    const resolvedPath = path.resolve(worktreeId);
    if (!resolvedPath.includes(`${path.sep}.worktrees${path.sep}`) && !syncFs.existsSync(resolvedPath)) {
      throw new Error(`Invalid worktreeId: '${worktreeId}' escapes worktrees root.`);
    }

    return resolvedPath;
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

    if (syncFs.existsSync(resolvedTarget)) {
      const realTarget = syncFs.realpathSync(resolvedTarget);
      if (realTarget !== canonicalWorktree && !realTarget.startsWith(canonicalWorktree + path.sep)) {
        throw new Error(
          `Containment error: Target path '${targetPath}' escapes worktree root '${worktreePath}'`
        );
      }
      return realTarget;
    }

    if (resolvedTarget !== canonicalWorktree && !resolvedTarget.startsWith(canonicalWorktree + path.sep)) {
      throw new Error(
        `Containment error: Target path '${targetPath}' escapes worktree root '${worktreePath}'`
      );
    }

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
  public async loadAgentContext(worktreePath: string, brief: string): Promise<string> {
    const contextSections: string[] = [];

    // 1. Repair agent prompt
    const repairPromptPath = path.resolve(process.cwd(), "src/agents/repair-agent.prompt.md");
    if (syncFs.existsSync(repairPromptPath)) {
      const promptContent = await fs.readFile(repairPromptPath, "utf-8");
      contextSections.push(`# System Prompt (Repair Agent)\n\n${promptContent}`);
    }

    // 2. Local worktree contract
    const contractPath = path.join(worktreePath, ".agents", "AGENT_CONTRACT.md");
    if (syncFs.existsSync(contractPath)) {
      const contractContent = await fs.readFile(contractPath, "utf-8");
      contextSections.push(`# Worktree Agent Contract\n\n${contractContent}`);
    }

    // 3. Explicit brief
    contextSections.push(`# Task Brief\n\n${brief}`);

    return contextSections.join("\n\n---\n\n");
  }

  /**
   * Spawns an isolated agent session locked to the given worktree.
   */
  public async dispatch(options: DispatchOptions): Promise<AgentSession> {
    const worktreePath = this.resolveWorktreePath(options.worktreeId, options.repo);

    if (!syncFs.existsSync(worktreePath)) {
      throw new Error(`Worktree path does not exist: ${worktreePath}`);
    }

    let branch = "agent/" + path.basename(worktreePath);
    let baseBranch = "main";
    try {
      const brRes = await runCommand("git", ["branch", "--show-current"], { cwd: worktreePath });
      if (brRes.exitCode === 0 && brRes.stdout.trim()) {
        branch = brRes.stdout.trim();
      }
    } catch {
      // ignore
    }

    const sessionId = `sess_${crypto.randomBytes(6).toString("hex")}`;
    const now = Date.now();

    const session: AgentSession = {
      sessionId,
      worktreeId: options.worktreeId,
      worktreePath,
      branch,
      baseBranch,
      repo: options.repo,
      brief: options.brief,
      model: options.model,
      state: "running",
      status: "running",
      startedAt: now,
      createdAt: now,
      updatedAt: now,
      lastCheckpoint: "worktree_setup",
      changedFiles: [],
      retries: 0,
      maxRetries: 3,
      transcript: [`[System]: Dispatch initiated with model ${options.model || "default"}`],
      logs: [`[${new Date(now).toISOString()}] Session ${sessionId} initialized in worktree ${worktreePath}`],
      lastVerification: null,
    };

    await this.saveSession(session);
    void this.runSessionProcess(session.sessionId);
    return session;
  }

  /**
   * Spawns the executor CLI in the session worktree and streams its
   * output into the session logs. Fire-and-forget: dispatch returns
   * immediately; completion flips the checkpoint to done/failed.
   * Set BOOMTICK_SESSION_EXEC=0 to disable (bookkeeping only).
   */
  public async runSessionProcess(sessionId: string): Promise<void> {
    const session = await this.loadSession(sessionId);
    if (!session) {
      return;
    }
    if (process.env.BOOMTICK_SESSION_EXEC === "0") {
      return;
    }
    const cli = process.env.BOOMTICK_EXECUTOR_CLI || "s5-coder";
    const model = session.model || process.env.BOOMTICK_EXECUTOR_MODEL || undefined;
    const context = await this.loadAgentContext(session.worktreePath, session.brief);
    const args = ["-p", "--system-prompt", context];
    if (model) {
      args.push("--model", model);
    }
    args.push(session.brief);

    await this.updateCheckpoint(sessionId, "executing", "running");

    await new Promise<void>((resolve) => {
      let child;
      try {
        child = spawn(cli, args, { cwd: session.worktreePath });
      } catch (err: any) {
        void this.appendLogs(sessionId, [`[exec] spawn failed: ${err.message}`])
          .then(() => this.updateCheckpoint(sessionId, "execution_failed", "failed"))
          .then(() => resolve());
        return;
      }
      let buffer = "";
      const pushLines = (chunk: Buffer) => {
        buffer += chunk.toString();
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        if (lines.length > 0) {
          void this.appendSessionLines(sessionId, lines);
        }
      };
      child.stdout.on("data", pushLines);
      child.stderr.on("data", pushLines);
      child.on("error", (err: Error) => {
        void this.appendLogs(sessionId, [`[exec] spawn failed: ${err.message}`])
          .then(() => this.updateCheckpoint(sessionId, "execution_failed", "failed"))
          .then(() => resolve());
      });
      child.on("close", (code: number | null) => {
        const tail = buffer.trim() ? [buffer.trim()] : [];
        void this.appendSessionLines(sessionId, tail)
          .then(() => this.updateCheckpoint(
            sessionId,
            code === 0 ? "execution_done" : "execution_failed",
            code === 0 ? "done" : "failed"
          ))
          .then(() => resolve());
      });
    });
  }

  /**
   * Appends streamed lines, capped so long runs cannot grow logs
   * without bound.
   */
  private async appendSessionLines(sessionId: string, lines: string[]): Promise<void> {
    const session = await this.loadSession(sessionId);
    if (!session) {
      return;
    }
    for (const line of lines) {
      if (session.logs.length >= MAX_SESSION_LOG_LINES) {
        session.logs.push("[exec] log truncated: line cap reached");
        break;
      }
      session.logs.push(line);
    }
    session.updatedAt = Date.now();
    await this.saveSession(session);
  }

  /**
   * Persists session data both in memory and to disk inside worktree (session.json).
   */
  public async saveSession(session: AgentSession): Promise<void> {
    this.sessions.set(session.sessionId, session);

    if (session.worktreePath && syncFs.existsSync(session.worktreePath)) {
      const sessionFile = path.join(session.worktreePath, "session.json");
      try {
        await fs.writeFile(sessionFile, JSON.stringify(session, null, 2), "utf-8");
      } catch {
        // ignore write errors if worktree is being removed
      }
    }
  }

  public async persistSession(sessionId: string): Promise<void> {
    const session = this.getSession(sessionId);
    await this.saveSession(session);
  }

  /**
   * Loads session from memory or disk.
   */
  public async loadSession(sessionId: string): Promise<AgentSession | null> {
    if (this.sessions.has(sessionId)) {
      return this.sessions.get(sessionId)!;
    }

    // Check under common worktrees paths if in active repo
    const repoRoot = this.getRepoRoot();
    const worktreesDir = path.resolve(repoRoot, ".worktrees");
    if (syncFs.existsSync(worktreesDir)) {
      try {
        const entries = await fs.readdir(worktreesDir, { withFileTypes: true });
        for (const entry of entries) {
          if (entry.isDirectory()) {
            const candidateFile = path.join(worktreesDir, entry.name, "session.json");
            if (syncFs.existsSync(candidateFile)) {
              try {
                const content = await fs.readFile(candidateFile, "utf-8");
                const data = JSON.parse(content) as AgentSession;
                if (data.sessionId === sessionId) {
                  this.sessions.set(sessionId, data);
                  return data;
                }
              } catch {
                // ignore corrupted session file
              }
            }
          }
        }
      } catch {
        // ignore
      }
    }

    return null;
  }

  /**
   * Updates session checkpoint and state.
   */
  public async updateCheckpoint(
    sessionId: string,
    checkpoint: string,
    state?: SessionState
  ): Promise<AgentSession> {
    const session = await this.loadSession(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }

    session.lastCheckpoint = checkpoint;
    if (state) {
      session.state = state;
    }
    session.updatedAt = Date.now();
    session.logs.push(`[${new Date().toISOString()}] Checkpoint: ${checkpoint} (state: ${session.state})`);

    await this.saveSession(session);
    return session;
  }

  /**
   * Appends logs to session transcript.
   */
  public async appendLogs(sessionId: string, newLogs: string[]): Promise<AgentSession> {
    const session = await this.loadSession(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }

    session.logs.push(...newLogs);
    session.updatedAt = Date.now();

    await this.saveSession(session);
    return session;
  }

  /**
   * Runs verification commands declared in the worktree's AGENT_CONTRACT.md.
   */
  public async runVerification(sessionId: string): Promise<SessionVerification> {
    const session = await this.loadSession(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }

    const contractPath = path.join(session.worktreePath, ".agents", "AGENT_CONTRACT.md");
    let testCommands: string[] = [];

    if (syncFs.existsSync(contractPath)) {
      const contractText = await fs.readFile(contractPath, "utf-8");
      const lines = contractText.split("\n");
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("testCommand:")) {
          testCommands.push(trimmed.replace(/^testCommand:\s*/, "").trim());
        }
        if (trimmed.startsWith("lintCommand:")) {
          testCommands.push(trimmed.replace(/^lintCommand:\s*/, "").trim());
        }
      }
    }

    if (testCommands.length === 0) {
      testCommands = ["npm test"];
    }

    let testsPassed = true;
    let errors: string | null = null;
    let lastExitCode: number | null = 0;

    for (const cmdStr of testCommands) {
      session.logs.push(`[Verification] Running: ${cmdStr}`);
      const parts = cmdStr.split(/\s+/);
      const prog = parts[0];
      const args = parts.slice(1);

      try {
        const res = await runCommand(prog, args, { cwd: session.worktreePath });
        if (res.exitCode !== 0) {
          testsPassed = false;
          errors = res.stderr || res.stdout;
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
  public async getStatus(sessionId: string): Promise<AgentSession> {
    const session = await this.loadSession(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }

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

  /**
   * Appends structured feedback and resumes bounded execution in the worktree.
   * Max retry bound: 3 attempts.
   */
  public async requestChanges(sessionId: string, message: string): Promise<AgentSession> {
    const session = this.getSession(sessionId);

    if (session.state === "abandoned") {
      throw new Error(`Cannot request changes on abandoned session: ${sessionId}`);
    }

    if (!message || message.trim().length === 0) {
      throw new Error("Message cannot be empty when requesting changes.");
    }

    const currentRetries = session.retries || 0;
    const maxRetries = session.maxRetries || 3;

    if (currentRetries >= maxRetries) {
      session.state = "failed";
      session.updatedAt = Date.now();
      session.transcript.push(`[System]: Retry budget of ${maxRetries} exceeded. Marking session failed.`);
      await this.persistSession(sessionId);
      throw new Error(`Retry budget of ${maxRetries} exceeded for session ${sessionId}.`);
    }

    session.retries = currentRetries + 1;
    session.brief += `\n\n[Change Request ${session.retries}]: ${message.trim()}`;
    session.transcript.push(`[User Feedback]: ${message.trim()}`);
    session.state = "running";
    session.updatedAt = Date.now();

    await this.persistSession(sessionId);
    return session;
  }

  /**
   * Marks session as completed / approved.
   */
  public async completeSession(sessionId: string, prUrl?: string): Promise<AgentSession> {
    const session = this.getSession(sessionId);
    session.state = "done";
    session.updatedAt = Date.now();
    if (prUrl) {
      session.pullRequestUrl = prUrl;
    }
    session.transcript.push(`[System]: Session completed successfully.`);
    await this.persistSession(sessionId);
    return session;
  }

  /**
   * Cancels session and cleans up worktree.
   */
  public async abandonSession(sessionId: string, baseRepoPath?: string): Promise<AgentSession> {
    const session = this.getSession(sessionId);
    session.state = "abandoned";
    session.updatedAt = Date.now();
    session.transcript.push(`[System]: Session abandoned and worktree removed.`);

    if (session.worktreePath) {
      try {
        await removeWorktree(session.worktreePath, baseRepoPath || session.repo || undefined);
      } catch (err) {
        try {
          await fs.rm(session.worktreePath, { recursive: true, force: true });
        } catch {
          // Ignore removal failure
        }
      }
    }

    return session;
  }

  /**
   * Queries status of session worktree: current state, modified files, diff stats, and verification status.
   */
  public async getSessionStatus(sessionId: string): Promise<{
    sessionId: string;
    state: SessionState;
    branch: string;
    baseBranch: string;
    modifiedFiles: string[];
    diffStat: { insertions: number; deletions: number; summary: string };
    lastVerification?: LastVerification | null;
  }> {
    const session = this.getSession(sessionId);
    const worktreePath = session.worktreePath;

    let modifiedFiles: string[] = [];
    let insertions = 0;
    let deletions = 0;
    let statSummary = "+0 / -0";

    if (worktreePath) {
      const statusRes = await runCommand("git", ["status", "--porcelain"], { cwd: worktreePath });
      if (statusRes.exitCode === 0) {
        modifiedFiles = statusRes.stdout
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
            return file.replace(/^"|"$/g, "");
          });
      }

      const base = session.baseBranch || "main";
      const diffStatRes = await runCommand(
        "git",
        ["diff", "--stat", `${base}...HEAD`],
        { cwd: worktreePath }
      );

      if (diffStatRes.exitCode === 0 && diffStatRes.stdout.trim().length > 0) {
        const lines = diffStatRes.stdout.trim().split("\n");
        const lastLine = lines[lines.length - 1];
        const insMatch = lastLine.match(/(\d+)\s+insertion/);
        const delMatch = lastLine.match(/(\d+)\s+deletion/);
        insertions = insMatch ? parseInt(insMatch[1], 10) : 0;
        deletions = delMatch ? parseInt(delMatch[1], 10) : 0;
        statSummary = `+${insertions} / -${deletions}`;
      }
    }

    return {
      sessionId: session.sessionId,
      state: session.state,
      branch: session.branch,
      baseBranch: session.baseBranch,
      modifiedFiles,
      diffStat: {
        insertions,
        deletions,
        summary: statSummary,
      },
      lastVerification: session.lastVerification,
    };
  }

  /**
   * Generates full unified diff from base branch using git diff <baseBranch>...HEAD and returns review outputs.
   */
  public async getReviewDiff(sessionId: string): Promise<{
    sessionId: string;
    baseBranch: string;
    branch: string;
    unifiedDiff: string;
    verificationOutputs?: LastVerification | null;
  }> {
    const session = this.getSession(sessionId);
    const worktreePath = session.worktreePath;
    const base = session.baseBranch || "main";

    let unifiedDiff = "";
    if (worktreePath) {
      const diffRes = await runCommand("git", ["diff", `${base}...HEAD`], { cwd: worktreePath });
      unifiedDiff = diffRes.stdout || "";
    }

    return {
      sessionId: session.sessionId,
      baseBranch: base,
      branch: session.branch,
      unifiedDiff,
      verificationOutputs: session.lastVerification,
    };
  }
}
