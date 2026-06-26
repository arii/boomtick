import { z } from "zod";

export const SendJulesMessageInputSchema = z.object({
  id: z.string(),
  message: z.string(),
});

export async function sendJulesMessageHandler(input: z.infer<typeof SendJulesMessageInputSchema>) {
  const apiKey = process.env.JULES_API_KEY;
  if (!apiKey) {
    throw new Error("JULES_API_KEY environment variable is not set.");
  }

  const cleanId = input.id.replace("sessions/", "");
  const response = await fetch(`https://jules.googleapis.com/v1alpha/sessions/${cleanId}:sendMessage`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": apiKey,
    },
    body: JSON.stringify({
      prompt: input.message,
    }),
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Jules API error (${response.status}): ${errText}`);
  }

  return {
    id: cleanId,
    status: "success",
    message: "Message sent successfully",
  };
}
