/**
 * Resolves the AI provider to be used for the current script execution.
 *
 * First checks for an explicit override via the `AI_PROVIDER_OVERRIDE` environment variable,
 * which is securely set by backward-compatible forwarding stubs. If no override is present,
 * falls back to reading the provider from the first CLI argument (`process.argv[2]`).
 *
 * Includes strict validation against allowed values to prevent arbitrary input injection.
 *
 * @returns {string} The resolved provider ('gemini' or 'github-models')
 * @throws {Error} If the resolved provider is not in the list of allowed values.
 */
export function getProvider(): string {
  const provider = process.env.AI_PROVIDER_OVERRIDE || process.argv[2];

  const allowedProviders = ['gemini', 'github-models'];
  if (!allowedProviders.includes(provider)) {
    throw new Error(`Invalid provider specified: ${provider}. Allowed values: ${allowedProviders.join(', ')}`);
  }

  return provider;
}
