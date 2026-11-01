import { AgentLogsInput, AgentLogsInputSchema } from "./contract.js";
import { SessionManager } from "../lib/session_manager.js";

export { AgentLogsInputSchema };

export async function agentLogsHandler(args: AgentLogsInput) {
  const parsed = AgentLogsInputSchema.parse(args);
  const manager = SessionManager.getInstance();

  return await manager.getLogs(parsed.sessionId, parsed.tail);
}
