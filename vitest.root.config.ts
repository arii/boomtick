import { defineConfig } from 'vitest/config';

// Root-only tests. MCP and workflows keep their own package configurations.
export default defineConfig({
  test: {
    globals: false,
    environment: 'node',
    include: ['tests/unit/**/*.test.ts'],
  },
});
