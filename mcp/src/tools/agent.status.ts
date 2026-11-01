import { AgentStatusInput, AgentStatusInputSchema } from "./contract.js";
import { SessionManager } from "../lib/session_manager.js";

export { AgentStatusInputSchema };

export async function agentStatusHandler(args: AgentStatusInput) {
  const parsed = AgentStatusInputSchema.parse(args);
  const manager = SessionManager.getInstance();

  const session = await manager.getStatus(parsed.sessionId);

  return {
    sessionId: session.sessionId,
    worktreeId: session.worktreeId,
    state: session.state,
    lastCheckpoint: session.lastCheckpoint,
    changedFiles: session.changedFiles,
    lastVerification: session.lastVerification || null,
  };
}
