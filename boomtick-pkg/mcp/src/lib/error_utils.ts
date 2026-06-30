/**
 * Sanitizes stderr from CLI commands to prevent implementation detail leakage
 * in error messages returned to the AI agent.
 */
export function sanitizeError(stderr: string): string {
  // Take first line and truncate to 200 chars to balance detail vs security
  return (stderr.split("\n")[0] || "Unknown error").slice(0, 200);
}
