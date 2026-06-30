import { z } from "zod";

export const GetJulesMessagesInputSchema = z.object({
  id: z.string(),
});

export async function getJulesMessagesHandler(input: z.infer<typeof GetJulesMessagesInputSchema>) {
  const apiKey = process.env.JULES_API_KEY;
  if (!apiKey) {
    throw new Error("JULES_API_KEY environment variable is not set.");
  }

  const cleanId = input.id.replace("sessions/", "");
  const response = await fetch(`https://jules.googleapis.com/v1alpha/sessions/${cleanId}/activities`, {
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
  const activities = data.activities || [];

  const messages = activities.map((act: any) => {
    const role = act.originator === "user" ? "user" : "jules";
    let content = "";

    if (act.userMessaged) {
      const um = act.userMessaged;
      content = typeof um === "string" ? um : (um.userMessage?.body || um.userMessage || "");
    } else if (act.progressUpdated) {
      content = act.progressUpdated.description || "";
    } else if (act.planGenerated) {
      const steps = act.planGenerated.plan?.steps || [];
      content = "Generated plan:\n" + steps.map((s: any) => `- ${s.description}`).join("\n");
    } else if (act.sessionCompleted) {
      content = "Session completed successfully.";
    }

    return {
      role,
      content,
      time: act.createTime,
    };
  }).filter((m: any) => m.content !== "");

  return {
    id: cleanId,
    messages,
  };
}
