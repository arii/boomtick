import { defineConfig } from 'tsup';

export default defineConfig({
  entry: {
    runner: 'scripts/impact-ai-code-review.ts',
    impact: 'scripts/impact-analysis.ts',
  },
  format: ['cjs'],
  outDir: 'dist',
  clean: true,
  noSplitting: true,
  noExternal: [/@octokit/],
  outExtension() {
    return {
      js: '.cjs',
    };
  },
});
