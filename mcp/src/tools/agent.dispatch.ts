import { AgentDispatchInput, AgentDispatchInputSchema } from "./contract.js";
import { SessionManager } from "../lib/session_manager.js";

export { AgentDispatchInputSchema };

export async function agentDispatchHandler(args: Partial<AgentDispatchInput> & { worktreeId: string; brief: string }) {
  const parsed = AgentDispatchInputSchema.parse(args);
  const manager = SessionManager.getInstance();

  const session = await manager.dispatch({
    worktreeId: parsed.worktreeId,
    brief: parsed.brief,
    model: parsed.model ?? null,
    repo: parsed.repo ?? null,
  });

  return {
    sessionId: session.sessionId,
    worktreeId: session.worktreeId,
    status: session.status,
    startedAt: session.startedAt,
  };
}
