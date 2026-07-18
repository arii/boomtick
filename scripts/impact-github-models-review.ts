/**
 * Forwarding stub to maintain backward compatibility for consumer package.json scripts.
 * Safely sets the provider via environment variables before executing the unified review module.
 */
process.env.AI_PROVIDER_OVERRIDE = 'github-models';
require('./impact-ai-review');
