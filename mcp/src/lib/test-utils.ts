import { vi } from "vitest";

/**
 * Shared test utilities for boomtick-mcp
 */

/**
 * Ensures JULES_API_KEY is set in the environment for tests that require it.
 * Should be called in beforeEach.
 */
export function setupTestEnv() {
  vi.stubEnv("JULES_API_KEY", "test-key");
}

/**
 * Resets the test environment.
 * Should be called in afterEach.
 */
export function teardownTestEnv() {
  vi.unstubAllEnvs();
  // Explicitly delete to satisfy strict isolation requirements if vi.unstubAllEnvs is not enough
  delete process.env.JULES_API_KEY;
}
