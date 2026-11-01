import fs from "fs/promises";
import { existsSync } from "fs";
import path from "path";
import { runCommand } from "./shell.js";
import { removeWorktree } from "./git.js";

export type SessionState = "running" | "done" | "failed" | "abandoned";

export interface LastVerification {
  testsPassed: boolean;
  errors?: string;
  exitCode?: number;
  output?: string;
}

export interface AgentSession {
  sessionId: string;
  worktreeId: string;
  worktreePath: string;
  branch: string;
  baseBranch: string;
  repo?: string;
  brief: string;
  state: SessionState;
  retries: number;
  maxRetries: number;
  transcript: string[];
  logs: string[];
  lastVerification?: LastVerification;
  createdAt: number;
  updatedAt: number;
  pullRequestUrl?: string;
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
   * Reset instance (primarily for tests).
   */
  public static resetInstance(): void {
    SessionManager.instance = new SessionManager();
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

  public async persistSession(sessionId: string): Promise<void> {
    const session = this.getSession(sessionId);
    if (!session.worktreePath || !existsSync(session.worktreePath)) {
      return;
    }
    const sessionFilePath = path.join(session.worktreePath, "session.json");
    try {
      await fs.writeFile(sessionFilePath, JSON.stringify(session, null, 2), "utf-8");
    } catch {
      // Ignore persistence errors if worktree is being removed or path unavailable
    }
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
        await removeWorktree(session.worktreePath, baseRepoPath || session.repo);
      } catch (err) {
        // Fallback: direct rimraf if git worktree prune fails
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
    lastVerification?: LastVerification;
  }> {
    const session = this.getSession(sessionId);
    const worktreePath = session.worktreePath;

    let modifiedFiles: string[] = [];
    let insertions = 0;
    let deletions = 0;
    let statSummary = "+0 / -0";

    if (worktreePath) {
      // Modified files via git status --porcelain
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

      // Diff stat against baseBranch
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
    verificationOutputs?: LastVerification;
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
