import { z } from "zod";
import { AgentDiscussInputSchema, AgentDiscussInput } from "./contract.js";
import { SessionManager } from "../lib/session_manager.js";
import { commitPatchHandler } from "./repo.commit_patch.js";
import { createPullRequestHandler } from "./github.create_pull_request.js";
import { removeWorktree } from "../lib/git.js";
import { runCommand } from "../lib/shell.js";

export { AgentDiscussInputSchema, AgentDiscussInput };

export async function agentDiscussHandler(rawArgs: AgentDiscussInput) {
  const args = AgentDiscussInputSchema.parse(rawArgs);
  const sessionManager = SessionManager.getInstance();

  // Validate topic input constraints before locking
  if (args.topic === "request-changes") {
    if (!args.message || args.message.trim().length === 0) {
      throw new Error("Message is required and cannot be empty when topic is 'request-changes'.");
    }
  }

  if (args.topic === "approve-merge") {
    if (!args.writeMode) {
      throw new Error("writeMode: true is required for approve-merge.");
    }
    if (!args.pushMode) {
      throw new Error("pushMode: true is required for approve-merge to push to remote and open PR.");
    }
  }

  if (args.topic === "abandon") {
    if (!args.writeMode) {
      throw new Error("writeMode: true is required for abandon.");
    }
  }

  // Acquire per-session lock to guarantee thread-safety and prevent concurrent conflicting discuss calls
  const releaseLock = await sessionManager.acquireLock(args.sessionId);

  try {
    const session = sessionManager.getSession(args.sessionId);

    switch (args.topic) {
      case "status": {
        const status = await sessionManager.getSessionStatus(args.sessionId);
        return {
          sessionId: args.sessionId,
          topic: args.topic,
          status: "success",
          data: status,
        };
      }

      case "review-diff": {
        const reviewDiff = await sessionManager.getReviewDiff(args.sessionId);
        return {
          sessionId: args.sessionId,
          topic: args.topic,
          status: "success",
          data: reviewDiff,
        };
      }

      case "request-changes": {
        const updated = await sessionManager.requestChanges(args.sessionId, args.message!);
        return {
          sessionId: args.sessionId,
          topic: args.topic,
          status: "success",
          message: `Feedback applied. Resumed execution on attempt ${updated.retries}/${updated.maxRetries}.`,
          data: {
            state: updated.state,
            retries: updated.retries,
            maxRetries: updated.maxRetries,
            brief: updated.brief,
          },
        };
      }

      case "approve-merge": {
        const worktreePath = session.worktreePath;
        const branch = session.branch;
        const baseBranch = session.baseBranch || "main";

        // 1. Stage and commit modified files if any uncommitted changes exist
        const statusRes = await runCommand("git", ["status", "--porcelain"], { cwd: worktreePath });
        const modifiedFiles = statusRes.stdout
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

        let commitSha: string | undefined;
        if (modifiedFiles.length > 0) {
          const commitResult = await commitPatchHandler({
            worktreePath,
            message: `feat(agent): verify and resolve task for session ${session.sessionId}`,
            allowedFiles: modifiedFiles,
            writeMode: true,
          });
          commitSha = commitResult.commitSha;
        } else {
          const headShaRes = await runCommand("git", ["rev-parse", "HEAD"], { cwd: worktreePath });
          commitSha = headShaRes.stdout.trim();
        }

        // 2. Push branch to remote origin
        const pushRes = await runCommand("git", ["push", "origin", branch], { cwd: worktreePath });
        if (pushRes.exitCode !== 0) {
          throw new Error(`Failed to push branch ${branch} to origin: ${pushRes.stderr || pushRes.stdout}`);
        }

        // 3. Open pull request using createPullRequestHandler
        const prTitle = `fix(agent): resolve session ${session.sessionId}`;
        const prBody = [
          `## Summary of Changes`,
          `Automated agent remediation session \`${session.sessionId}\`.`,
          ``,
          `### Task Brief`,
          `${session.brief}`,
          ``,
          `### Verification Details`,
          session.lastVerification?.testsPassed
            ? `✅ Automated verification tests passed.`
            : `⚠️ Verification status: ${session.lastVerification?.errors || "No errors recorded."}`,
        ].join("\n");

        const prResult = await createPullRequestHandler({
          title: prTitle,
          body: prBody,
          head: branch,
          base: baseBranch,
          draft: false,
          repo: args.repo || session.repo,
        });

        // 4. Clean up the worktree
        await removeWorktree(worktreePath, args.repo || session.repo);

        // 5. Complete session
        await sessionManager.completeSession(args.sessionId, prResult.url);

        return {
          sessionId: args.sessionId,
          topic: args.topic,
          status: "success",
          message: `Branch pushed and pull request opened at ${prResult.url}. Worktree cleaned up.`,
          data: {
            pullRequestUrl: prResult.url,
            branch,
            commitSha,
          },
        };
      }

      case "abandon": {
        const abandoned = await sessionManager.abandonSession(args.sessionId, args.repo ?? undefined);
        return {
          sessionId: args.sessionId,
          topic: args.topic,
          status: "success",
          message: `Session ${abandoned.sessionId} abandoned and worktree removed.`,
          data: {
            state: abandoned.state,
          },
        };
      }

      default: {
        throw new Error(`Unknown topic: ${(args as any).topic}`);
      }
    }
  } finally {
    releaseLock();
  }
}
