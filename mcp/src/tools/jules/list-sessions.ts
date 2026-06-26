import { z } from "zod";
import { JulesSession, JulesStatus } from "../types.js";

export const ListJulesSessionsInputSchema = z.object({
  pageSize: z.number().optional(),
  pageToken: z.string().optional(),
});

export async function listJulesSessionsHandler(input: z.infer<typeof ListJulesSessionsInputSchema>): Promise<JulesSession[]> {
  ListJulesSessionsInputSchema.parse(input);
  const apiKey = process.env.JULES_API_KEY;
  if (!apiKey) {
    throw new Error("JULES_API_KEY environment variable is not set.");
  }

  if (apiKey.length < 20) {
    throw new Error("JULES_API_KEY appears to be invalid (too short).");
  }

  const url = new URL("https://jules.googleapis.com/v1alpha/sessions");
  url.searchParams.set("pageSize", (input.pageSize ?? 100).toString());
  if (input.pageToken) {
    url.searchParams.set("pageToken", input.pageToken);
  }

  let response;
  try {
    response = await fetch(url.toString(), {
      method: "GET",
      headers: {
        "x-goog-api-key": apiKey,
      },
    });
  } catch (e) {
    throw new Error(`Network error fetching sessions: ${e instanceof Error ? e.message : String(e)}`);
  }

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Jules API error (${response.status}): ${errText}`);
  }

  const data = (await response.json()) as any;
  const sessions = data.sessions || [];

  return sessions.map((session: any) => {
    const name = session.name || "";
    const id = name.startsWith("sessions/") ? name.substring(9) : name;

    let status: JulesStatus = "PENDING";
    if (session.state === "SUCCEEDED" || session.state === "COMPLETED") status = "COMPLETED";
    else if (session.state === "FAILED" || session.state === "CANCELLED" || session.state === "TERMINATED") status = "FAILED";
    else if (session.state === "IN_PROGRESS") status = "IN_PROGRESS";

    let pullRequestUrl: string | undefined;
    if (session.outputs && Array.isArray(session.outputs)) {
      for (const output of session.outputs) {
        if (output.pullRequest && output.pullRequest.url) {
          pullRequestUrl = output.pullRequest.url;
          break;
        }
      }
    }

    return {
      id,
      status,
      createdAt: session.createTime ? new Date(session.createTime) : new Date(),
      pullRequestUrl,
    };
  });
}
