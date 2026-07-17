export interface PromptCategory {
  id: string;
  name: string;
  matcher: (files: string[]) => boolean;
  guidance: string;
}

export const PROMPT_CATEGORIES: PromptCategory[] = [
  {
    id: 'ci-cd',
    name: 'CI/CD Workflows',
    // Scoped to actual workflow/action files, not every .yml in the repo
    // (which would also match unrelated config like Renovate, docs frontmatter, etc.)
    matcher: (files) => files.some(f =>
      f.startsWith('.github/workflows/') || f.startsWith('.github/actions/')
    ),
    guidance: `CI/CD:
- \`if: always()\` + \`continue-on-error: true\` is INTENTIONAL.
- \`\${{ secrets.X }}\` is GHA syntax.
- YAML paths MUST remain direct and explicit (no complex nested scanning or folder loops).
- Blocking: missing secret production, invalid \`needs:\`, YAML syntax errors.`,
  },
  {
    id: 'llm-integration',
    name: 'LLM Client Integrations',
    matcher: (files) => files.some(f =>
      f.includes('clients/') || f.endsWith('CodeReviewClient.ts') || f.endsWith('VisualReviewClient.ts') || f.includes('modelPicker.ts')
    ),
    guidance: `LLM Clients:
- \`ChatOpenAI\` + \`baseURL\` override == GitHub Models.
- Model names (gpt-4o-mini) refer to GitHub's catalog, not OpenAI's.
- Gemini uses \`ChatGoogleGenerativeAI\`.
- Blocking: broken \`baseURL\`, auth, or fetch URLs.`,
  },
  {
    id: 'build-config',
    name: 'Build/Bundler Configurations',
    matcher: (files) => files.some(f =>
      f.includes('vite.config') || (f.includes('tsconfig') && f.endsWith('.json')) ||
      f === 'package.json' || f.includes('rollup.config') || f === '.npmrc'
    ),
    guidance: `Build Config:
- package.json: flag bumps ONLY if they break builds.
- tsconfig/vite: blocking ONLY if they break imports.
- BANNED: \`use-node-version\` in \`.npmrc\`. Use \`engines\` in package.json.`,
  },
  {
    id: 'react-components',
    name: 'React Components',
    matcher: (files) => files.some(f => f.endsWith('.tsx') || f.endsWith('.jsx')),
    guidance: `React:
- Audit: stale closures, missing dependencies, unnecessary effects/memos, duplicated/derived state, prop drilling, unnecessary renders.
- Blocking: hook rule violations (conditional calls), demonstrably stale dependency arrays.
- Tokens: BANNED: raw hex colors in TSX. Use tokens.css.`,
  },
  {
    id: 'typescript-types',
    name: 'TypeScript Definitions',
    matcher: (files) => files.some(f => f.endsWith('.d.ts') || f.endsWith('Types.ts') || f.endsWith('.ts')),
    guidance: `TS:
- Report: 'any', unsafe casts, ignored nulls, unreachable code.
- Blocking: type changes that demonstrably break visible usage sites.
- Ignore: style preferences.`,
  },
  {
    id: 'python-scripts',
    name: 'Python Scripts',
    matcher: (files) => files.some(f => f.endsWith('.py')),
    guidance: `Python:
- \`sys.path\` manipulation is INTENTIONAL for CI patterns.
- \`logging\` is standard; do not suggest \`print()\`.
- Blocking: incorrect exit codes (e.g. \`sys.exit(0)\` in error paths), uncaught exceptions.`,
  },
  {
    id: 'tests',
    name: 'Test Files',
    matcher: (files) => files.some(f =>
      f.includes('.test.') || f.includes('.spec.') || f.startsWith('tests/')
    ),
    guidance: `Tests:
- Mocking/spying is standard hygiene.
- Blocking: assertions checking the wrong thing, tautological tests (pass regardless of impl).
- Edge cases: suggest missing coverage as non-blocking notes.`,
  },
];
