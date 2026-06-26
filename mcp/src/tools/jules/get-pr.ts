import { z } from "zod";

export const GetJulesPullRequestInputSchema = z.object({
  id: z.string(),
});

export async function getJulesPullRequestHandler(input: z.infer<typeof GetJulesPullRequestInputSchema>) {
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
    id: cleanId,
    pullRequestUrl,
  };
}
