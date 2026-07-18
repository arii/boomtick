import { GitHubModelFactory, ReviewOptions } from "./factory";

export async function runReview(options: ReviewOptions): Promise<string> {
  const client = GitHubModelFactory.getClient();
  const fallbackChain = GitHubModelFactory.getFallbackChain();

  for (const model of fallbackChain) {
    try {
      console.log(`[AI Review] Attempting review with model: ${model}`);

      const response = await client.chat.completions.create({
        model: model,
        messages: [
          {
            role: "system",
            content: `You are an expert automated code review agent. Rules to enforce:\n${options.rules.join("\n")}`
          },
          {
            role: "user",
            content: `Review the following Pull Request changes:\n\n${options.prContent}`
          }
        ],
        temperature: 0.2,
      });

      return response.choices[0].message.content || "No review feedback provided.";

    } catch (error) {
      const err = error as { status?: number; message?: string };
      // Check if it's a rate limit (429) or temporary server issue
      if (err?.status === 429) {
        console.warn(`[AI Review Warning] Usage/Rate limit hit for ${model}. Rotating to next backup...`);
      } else {
        console.warn(`[AI Review Warning] Model ${model} encountered an error: ${err?.message || error}. Trying backup...`);
      }
    }
  }

  throw new Error("All requested GitHub Model providers and fallbacks failed or exhausted their usage limits.");
}
