import { z } from "zod";
import { JulesSession, JulesStatus } from "../types.js";

export const GetJulesSessionInputSchema = z.object({
  id: z.string(),
});

export async function getJulesSessionHandler(input: z.infer<typeof GetJulesSessionInputSchema>): Promise<JulesSession> {
  const apiKey = process.env.JULES_API_KEY;
  if (!apiKey) {
    throw new Error("JULES_API_KEY environment variable is not set.");
  }

  const cleanId = input.id.replace("sessions/", "");
  const response = await fetch(`https://jules.googleapis.com/v1alpha/sessions/${cleanId}`, {
    method: "GET",
    headers: {
      "x-goog-api-key": apiKey,
    },
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Jules API error (${response.status}): ${errText}`);
  }

  const data = (await response.json()) as any;
  const name = data.name || "";
  const id = name.startsWith("sessions/") ? name.substring(9) : name;

  let status: JulesStatus = "PENDING";
  if (data.state === "SUCCEEDED" || data.state === "COMPLETED") status = "COMPLETED";
  else if (data.state === "FAILED" || data.state === "CANCELLED" || data.state === "TERMINATED") status = "FAILED";
  else if (data.state === "IN_PROGRESS") status = "IN_PROGRESS";

  let pullRequestUrl: string | undefined;
  if (data.outputs && Array.isArray(data.outputs)) {
    for (const output of data.outputs) {
      if (output.pullRequest && output.pullRequest.url) {
        pullRequestUrl = output.pullRequest.url;
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
