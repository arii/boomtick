import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    exclude: ["node_modules", "dist"],
    include: ["src/**/*.test.ts", "../tests/**/*.test.ts", "../scripts/**/*.test.ts"],
  },
});
