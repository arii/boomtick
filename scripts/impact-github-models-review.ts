/**
 * Forwarding stub to maintain backward compatibility for consumer package.json scripts.
 * Safely injects the expected CLI argument before executing the unified review module.
 */
(async () => {
  process.argv.splice(2, 0, 'github-models');
  await import('./impact-ai-review');
})().catch(error => {
  console.error(error);
  process.exit(1);
});
