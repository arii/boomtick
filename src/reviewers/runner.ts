import { GitHubModelFactory, ReviewOptions } from "./factory";

interface ApiError {
  status?: number;
  message?: string;
}

function isApiError(err: unknown): err is ApiError {
  return (
    typeof err === "object" &&
    err !== null &&
    ("status" in err || "message" in err)
  );
}

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
            // Wrap the prContent in XML tags to establish structural boundaries and prevent prompt injection
            content: `Review the following Pull Request changes:\n\n<pr_content>\n${options.prContent}\n</pr_content>`
          }
        ],
        temperature: 0.2,
      });

      return response.choices[0].message.content || "No review feedback provided.";

    } catch (error) {
      // Use the custom type guard for safe error property access
      if (isApiError(error)) {
        if (error.status === 429) {
          console.warn(`[AI Review Warning] Usage/Rate limit hit for ${model}. Rotating to next backup...`);
        } else {
          console.warn(`[AI Review Warning] Model ${model} encountered an error: ${error.message || error}. Trying backup...`);
        }
      } else {
        const errorMsg = error instanceof Error ? error.message : String(error);
        console.warn(`[AI Review Warning] Model ${model} encountered an unexpected error: ${errorMsg}. Trying backup...`);
      }
    }
  }

  throw new Error("All requested GitHub Model providers and fallbacks failed or exhausted their usage limits.");
}
