import { z } from "zod";
import { JulesSession } from "../types.js";

export const CancelJulesSessionInputSchema = z.object({
  id: z.string(),
});

export async function cancelJulesSessionHandler(input: z.infer<typeof CancelJulesSessionInputSchema>): Promise<JulesSession> {
  const apiKey = process.env.JULES_API_KEY;
  if (!apiKey) {
    throw new Error("JULES_API_KEY environment variable is not set.");
  }

  const cleanId = input.id.replace("sessions/", "");
  const response = await fetch(`https://jules.googleapis.com/v1alpha/sessions/${cleanId}`, {
    method: "DELETE",
    headers: {
      "x-goog-api-key": apiKey,
    },
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Jules API error (${response.status}): ${errText}`);
  }

  return {
    id: cleanId,
    status: "FAILED",
    createdAt: new Date(),
  };
}
