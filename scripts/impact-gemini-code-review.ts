/**
 * Forwarding stub to maintain backward compatibility for consumer package.json scripts.
 * Safely sets the provider via environment variables before executing the unified code review module.
 */
process.env.AI_PROVIDER_OVERRIDE = 'gemini';
require('./impact-ai-code-review');
