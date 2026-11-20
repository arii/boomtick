# Test commands

From the repository root:

- `pnpm test` runs root TypeScript unit tests, then the MCP and workflows suites.
- `pnpm run test:unit` runs only `tests/unit/**/*.test.ts` using the root
  `vitest.root.config.ts`. Tests import Vitest helpers explicitly; globals are disabled.
  This includes the injected Gemini catalog assertion, with its mock isolated to
  that test file.
- `pnpm run test:python` runs the Python CLI suite in `cli/tests`.
- `td test cli` runs the same Python suite from the installed CLI package's root,
  regardless of the caller's current directory. It performs the normal runtime
  check first.

The MCP and workflows packages keep their own Vitest configurations. The root
runner does not collect their tests a second time.
