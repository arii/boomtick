/**
 * Forwarding stub to maintain backward compatibility for consumer package.json scripts.
 * Safely injects the expected CLI argument before executing the unified code review module.
 */
(async () => {
  process.argv.splice(2, 0, 'gemini');
  await import('./impact-ai-code-review');
})().catch(error => {
  console.error(error);
  process.exit(1);
});
