/**
 * Forwarding stub to maintain backward compatibility for consumer package.json scripts.
 * Safely injects the expected CLI argument before executing the unified review module.
 */
process.argv.splice(2, 0, 'github-models');
require('./impact-ai-review');
