import { JulesSession, JulesStatus } from "../types.js";

export function parseJulesSession(data: any): JulesSession {
  const name = data.name || "";
  const id = name.startsWith("sessions/") ? name.substring(9) : name;

  let status: JulesStatus = "PENDING";
  if (data.state === "SUCCEEDED" || data.state === "COMPLETED") status = "COMPLETED";
  else if (data.state === "FAILED" || data.state === "CANCELLED" || data.state === "TERMINATED") status = "FAILED";
  else if (data.state === "IN_PROGRESS") status = "IN_PROGRESS";

  let pullRequestUrl: string | undefined;
  if (data.outputs && Array.isArray(data.outputs)) {
    for (const out of data.outputs) {
      if (out.pullRequest && out.pullRequest.url) {
        pullRequestUrl = out.pullRequest.url;
        break;
      }
    }
  }

  return {
    id,
    status,
    createdAt: data.createTime ? new Date(data.createTime) : new Date(),
    pullRequestUrl,
  };
}
