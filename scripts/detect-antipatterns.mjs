import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { execFileSync } from 'child_process';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

/**
 * Default list of directories or individual files to audit.
 */
const CHECK_PATHS = [
  'src/features',
  'src/pages',
  'src/components',
  'src/layouts',
  'src/styles',
  'src/providers',
  'src/hooks',
  'src/lib',
  'src/App.tsx',
  '.github/workflows',
  '.npmrc'
];

const AUDIT_EXTENSIONS = ['.ts', '.tsx', '.yml', '.css', '.scss', '.npmrc'];

function collectAuditFiles(targets) {
  const resolvedTargets = targets.length > 0 ? targets : CHECK_PATHS;
  const results = new Set();

  const isAuditFile = (filepath) => {
    return AUDIT_EXTENSIONS.some(ext => filepath.endsWith(ext));
  };

  const walk = (dir) => {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
        walk(fullPath);
      } else if (isAuditFile(fullPath)) {
        results.add(fullPath);
      }
    }
  };

  for (const target of resolvedTargets) {
    const absoluteTarget = path.isAbsolute(target) ? target : path.join(ROOT, target);
    if (!fs.existsSync(absoluteTarget)) continue;
    const stat = fs.statSync(absoluteTarget);

    if (stat.isDirectory()) {
      walk(absoluteTarget);
    } else if (isAuditFile(absoluteTarget)) {
      results.add(absoluteTarget);
    }
  }

  return Array.from(results);
}

const LAYOUT_SUGGESTIONS = {
  'flex flex-col': '<Stack direction="col">',
  'flex flex-row': '<Stack direction="row">',
  'flex items-center': '<Stack align="center">',
  'flex justify-between': '<Stack justify="between">',
  'grid grid-cols': '<Grid cols={...}>',
};

// Modularized linting configuration
const CONFIG = {
  allowedColors: [
    'bg', 'surface', 'surface-alt', 'accent', 'accent-brand', 'accent-navy',
    'accent-purple', 'accent-magenta', 'accent-sky',
    'text-main', 'text-body', 'text-dim', 'line', 'white', 'black',
    'transparent', 'current', 'yellow-400', 'emerald-500', 'red-500',
    'amber-500', 'success', 'error', 'warning'
  ],
  allowedTextUtils: ['left', 'right', 'center', 'justify', 'uppercase', 'lowercase', 'capitalize', 'normal-case', 'italic', 'not-italic', 'pretty', 'font-light'],
  allowedTextSizes: ['xs', 'sm', 'base', 'lg', 'xl', '2xl', '3xl', '4xl', '5xl', '6xl', '7xl', '8xl', '9xl'],
  rules: [
    {
      name: 'Arbitrary Value',
      pattern: /-\[.*?\]/g,
      severity: 'minor',
      message: 'Avoid arbitrary values like -[...]. Use design tokens instead.'
    },
    {
      name: 'Raw Layout/Spacing',
      pattern: /\b(flex|grid|items-|justify-|p[xytrbl]?-|m[xytrbl]?-|gap-)\b/,
      isClassNameRule: true,
      severity: 'minor',
      message: 'Use <Box />, <Stack />, or <Grid /> primitives for layout and spacing.'
    },
    {
      name: 'div Layout',
      pattern: /<div\s+[^>]*?className=["'](.*?(?:flex|grid|p-|m-|gap-).*?)["']/g,
      severity: 'minor',
      message: 'Avoid using <div> for layout. Use layout primitives from src/layouts/.'
    },
    {
      name: 'HashRouter Usage',
      pattern: /HashRouter/g,
      severity: 'major',
      message: 'HashRouter is banned. Use createBrowserRouter (AGENTS.md §9)'
    },
    {
      name: 'Unnecessary React Import',
      pattern: /import\s+React\s+from\s+['"]react['"]/g,
      severity: 'minor',
      message: 'Unnecessary React import — React 17+ (AGENTS.md §4)'
    },
    {
      name: 'Inline Styles',
      pattern: /style=\{\{/g,
      severity: 'major',
      message: 'Inline styles are banned. Use design tokens (AGENTS.md §11)'
    },
    {
      name: 'Arbitrary Pixel Value',
      pattern: /text-\[\d+px\]/g,
      severity: 'minor',
      message: 'Arbitrary px Tailwind value. Use design tokens (AGENTS.md §1)'
    },
    {
      name: 'Raw Hex Color',
      pattern: /bg-\[#/g,
      severity: 'minor',
      message: 'Raw hex color in Tailwind. Use CSS variables from tokens.css'
    },
    {
      name: 'Arbitrary Text Size',
      pattern: /className=".*?text-\[\d/g,
      severity: 'minor',
      message: 'Arbitrary text size. Use typeSizes from design-tokens.ts'
    },
    {
      name: 'Bare env: Key',
      pattern: /^([ \t]*)env:[ \t]*(?!\r?\n\1[ \t]+)/m,
      severity: 'major',
      message: 'Bare env: keys are invalid in GitHub Actions workflows. Provide values or remove the key.',
      filePattern: /\.yml$/
    },
    {
      name: 'Raw Hex Color (CSS)',
      pattern: /(?<!#|[\w-])#([0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![\w-])/g,
      severity: 'minor',
      message: 'Raw hex color in CSS. Use design tokens or CSS variables.',
      filePattern: /\.(css|scss|tsx|ts)$/
    },
    {
      name: 'Hardcoded Pixel Value (CSS)',
      pattern: /(?<![\w-])\d+px(?![\w-])/g,
      severity: 'minor',
      message: 'Avoid hardcoded pixel values in CSS. Use design tokens.',
      filePattern: /\.(css|scss|tsx|ts)$/
    },
    {
      name: 'Forbidden .npmrc property',
      pattern: /use-node-version/g,
      severity: 'major',
      message: 'use-node-version is forbidden in .npmrc as it breaks Vercel deployments. Use "engines" in package.json instead.',
      filePattern: /\.npmrc$/
    }
  ],
  deprecated: {
    assets: { 'accent-brand': 'accent', 'useSearch': 'useSearchParam' },
    paths: { 'src/components/common/': 'src/components/ui/' }
  },
  existingComponents: {
    'Box': 'src/layouts/Box.tsx', 'Stack': 'src/layouts/Stack.tsx', 'Grid': 'src/layouts/Grid.tsx',
    'Text': 'src/layouts/Text.tsx', 'Button': 'src/layouts/Button.tsx', 'ContentCard': 'src/components/ui/ContentCard.tsx',
    'PageHeader': 'src/components/ui/PageHeader.tsx', 'FilterBar': 'src/components/ui/FilterBar.tsx',
    'FolioGrid': 'src/components/ui/FolioGrid.tsx', 'Skeleton': 'src/components/ui/Skeleton.tsx',
    'ViewToggle': 'src/components/ui/ViewToggle.tsx', 'ListRow': 'src/components/ui/ListRow.tsx',
    'MarkdownRenderer': 'src/components/ui/MarkdownRenderer.tsx', 'DetailLayout': 'src/components/layout/DetailLayout.tsx',
    'useSearchParam': 'src/hooks/useSearchParam.ts', 'useHotkeys': 'src/hooks/useHotkeys.ts', 'safeSearch': 'src/lib/utils.ts',
  },
  requiredContentFields: ['type', 'title', 'date', 'author', 'category', 'excerpt']
};

function checkContent(content, filepath = 'unknown') {
  if (content.includes('// impeccable-ignore-file') || content.includes('/* impeccable-ignore-file */')) return [];
  const contentWithoutComments = content.replace(/\/\*[\s\S]*?\*\/|\/\/.*/g, (match) => ' '.repeat(match.length));

  const violations = [];

  // Helper to get line number from index efficiently
  const lineOffsets = [0];
  for (let i = 0; i < content.length; i++) {
    if (content[i] === '\n') lineOffsets.push(i + 1);
  }
  const getLineNumber = (index) => {
    let low = 0, high = lineOffsets.length - 1;
    while (low <= high) {
      const mid = Math.floor((low + high) / 2);
      if (lineOffsets[mid] <= index) low = mid + 1;
      else high = mid - 1;
    }
    return low;
  };

  // Pre-compiled rules and helper utilities
  const lines = content.split('\n');
  const layoutRule = CONFIG.rules.find(r => r.name === 'Raw Layout/Spacing');
  const suggestionsEntries = Object.entries(LAYOUT_SUGGESTIONS);

  // 1. Multi-line and General Rules (Global Scanner)
  CONFIG.rules
    .filter(r => !r.isClassNameRule)
    .forEach(rule => {
      if (rule.filePattern && !rule.filePattern.test(filepath)) return;
      const flags = (rule.name === 'div Layout' ? 'gs' : 'g') + (rule.pattern.multiline ? 'm' : '');
      const regex = new RegExp(rule.pattern.source, flags);
      const matches = contentWithoutComments.matchAll(regex);

      for (const match of matches) {
        const lineNum = getLineNumber(match.index);
        const lineText = lines[lineNum - 1] || '';
        if (lineText.includes('// impeccable-ignore') || lineText.includes('/* impeccable-ignore */')) continue;

        violations.push({
          line: lineNum,
          pattern: rule.name,
          severity: rule.severity || 'minor',
          value: match[0].length > 60 ? match[0].substring(0, 60).replace(/\s+/g, ' ') + '...' : match[0].replace(/\s+/g, ' '),
          message: rule.message
        });
      }
    });

  // 2. ClassName/Apply Specific Rules (Global Scanner)
  const stylingPatterns = [
    { regex: /className=["'](.*?)["']/gs, group: 1 },
    { regex: /@apply (.*?);/gs, group: 1 }
  ];

  for (const { regex, group } of stylingPatterns) {
    for (const match of content.matchAll(regex)) {
      const lineNum = getLineNumber(match.index);
      const lineText = lines[lineNum - 1] || '';
      if (lineText.includes('// impeccable-ignore') || lineText.includes('/* impeccable-ignore */')) continue;

      const classStr = match[group];
    const classes = classStr.split(/\s+/);

    classes.forEach(cls => {
      // Raw Layout/Spacing
      if (layoutRule.pattern.test(cls)) {
        violations.push({
          line: lineNum,
          pattern: layoutRule.name,
          severity: layoutRule.severity || 'minor',
          value: cls,
          message: layoutRule.message
        });
      }

      // Colors check
      if (/^(?:[a-z-]+:)?(bg|text|fill)-/.test(cls) && !cls.includes('bg-gradient-')) {
        if (CONFIG.allowedColors.includes(cls) || cls.startsWith('brand-')) return;
        const colorMatch = cls.match(/^(?:[a-z-]+:)?(bg|text|fill)-([a-z0-9/-]+)$/);
        if (colorMatch) {
          const prefix = colorMatch[1];
          const baseColor = colorMatch[2].split('/')[0];
          const fullToken = `${prefix}-${baseColor}`;
          const isAllowed = CONFIG.allowedColors.includes(baseColor) ||
                            CONFIG.allowedColors.includes(fullToken) ||
                            CONFIG.allowedTextUtils.includes(baseColor) ||
                            CONFIG.allowedTextSizes.includes(baseColor) ||
                            baseColor.startsWith('brand-') ||
                            fullToken.startsWith('brand-');

          if (!isAllowed) {
            violations.push({
              line: lineNum,
              pattern: 'Non-token Color/Size',
              severity: 'minor',
              value: cls,
              message: `Class '${cls}' uses a value that is not a recognized design token.`
            });
          }
        }
      }
    });

    // Layout Suggestions
    suggestionsEntries.forEach(([pattern, suggestion]) => {
      if (classStr.includes(pattern)) {
        if (!violations.some(v => v.line === lineNum && v.pattern === 'Layout Suggestion' && v.value === pattern)) {
          violations.push({
            line: lineNum,
            pattern: 'Layout Suggestion',
            severity: 'minor',
            value: pattern,
            message: `Consider replacing '${pattern}' with ${suggestion}`
          });
        }
      }
    });
    }
  }

  // 3. CSS Specific checks (excluding @apply which is handled above)
  // For CSS files, we want to ensure standard properties don't use raw hex/px
  // though they are already covered by the global rules in step 1.

  // 4. Contrast safety heuristic for inverse/gradient hero panels.
  // Single-pass sliding window: when an industrial gradient line is seen,
  // inspect nearby headline/body Text lines for explicit inverse-safe styling.
  let activeGradientWindowUntil = -1;
  for (let i = 0; i < lines.length; i++) {
    const lineNum = i + 1;
    const line = lines[i];

    if (line.includes('industrial-gradient')) {
      activeGradientWindowUntil = Math.max(activeGradientWindowUntil, lineNum + 30);
      continue;
    }
    if (activeGradientWindowUntil < lineNum || !line.includes('<Text') || line.includes('// impeccable-ignore') || line.includes('/* impeccable-ignore */')) continue;

    const isHeadlineOrBody = /variant="(?:headline|body)"/.test(line);
    const hasInverseColor = /color="(?:white|bg)"/.test(line);
    const hasIntent = /intent="/.test(line);
    if (isHeadlineOrBody && !hasInverseColor && !hasIntent) {
      violations.push({
        line: lineNum,
        pattern: 'Contrast Risk (Inverse Surface)',
        severity: 'major',
        value: line.trim().slice(0, 80),
        message: 'Text near industrial gradient must set inverse color token (white/bg) or intent for reliable contrast.'
      });
    }
  }

  // Sort violations by line number
  return violations.sort((a, b) => a.line - b.line);
}

function checkFile(filepath) {
  const content = fs.readFileSync(filepath, 'utf8');
  return checkContent(content, filepath);
}

function checkPRScope() {
  try {
    const scopeCheckScript = path.join(__dirname, "../boomtick-pkg/cli/dev_tools/scope_check.py");
    const output = execFileSync("python3", [scopeCheckScript], { encoding: "utf8", stdio: ['inherit', 'pipe', 'pipe'] }).trim();
    if (output) {
      console.log(`\x1b[33m⚠️  ${output}\x1b[0m\n`);
    }
  } catch (error) {
    // If the error message itself is present and is not just a standard shell error, report it
    if (error.stderr && error.stderr.trim()) {
      console.error(`\x1b[31m❌ Scope check failed:\x1b[0m\n${error.stderr}`);
    } else if (error.message) {
      console.error(`\x1b[31m❌ Scope check error:\x1b[0m ${error.message}`);
    }
    // Don't exit here as scope check is usually a non-blocking warning
  }
}

function generateTodoFile(allViolations) {
  let todoContent = "# UI Anti-Pattern TODO List\n\n";
  todoContent += "This list is automatically generated from the audit report. Fix these anti-patterns to adhere to the project design system.\n\n";

  for (const [file, violations] of Object.entries(allViolations)) {
    todoContent += `## ${file}\n`;
    violations.forEach(v => {
      todoContent += `- [ ] Line ${v.line}: [${v.pattern}] ${v.value} - ${v.message}\n`;
    });
    todoContent += "\n";
  }

  fs.writeFileSync(path.join(ROOT, 'TODO_ANTIPATTERNS.md'), todoContent);
}

const args = process.argv.slice(2);
const isJson = args.includes('--json');
const isCountOnly = args.includes('--count-only');
const shouldGenerateTodo = args.includes('--todo');
const targets = args.filter(arg => !arg.startsWith('--'));

const allViolations = {};

export { checkContent, collectAuditFiles, checkFile };

async function runAudit() {
  // Prevent running the main logic when imported as a module in tests
  if (process.argv[1] !== fileURLToPath(import.meta.url)) return;

  if (!isJson && !isCountOnly) {
    console.log('\x1b[34m🔍 Scanning for UI anti-patterns...\x1b[0m\n');
    checkPRScope();
  }

  if (targets.includes('-')) {
    let stdinContent = '';
    process.stdin.setEncoding('utf8');
    for await (const chunk of process.stdin) {
      stdinContent += chunk;
    }
    const violations = checkContent(stdinContent);
    if (violations.length > 0) {
      allViolations['stdin'] = violations;
    }
  } else {
    const files = collectAuditFiles(targets);

    files.forEach(filepath => {
      if (AUDIT_EXTENSIONS.some(ext => filepath.endsWith(ext))) {
        const violations = checkFile(filepath);
        if (violations.length > 0) {
          allViolations[path.relative(ROOT, filepath)] = violations;
        }
      }
    });
  }

  const totalViolations = Object.values(allViolations).flat().length;

  if (isCountOnly) {
    process.stdout.write(totalViolations.toString() + '\n');
    process.exit(0);
  }

  if (isJson) {
    process.stdout.write(JSON.stringify({
      violations: allViolations,
      config: {
        deprecated: CONFIG.deprecated,
        existingComponents: CONFIG.existingComponents,
        requiredContentFields: CONFIG.requiredContentFields
      }
    }, null, 2));
    process.exit(totalViolations > 0 ? 1 : 0);
  }

  if (totalViolations === 0) {
    console.log('\x1b[32m✔ No anti-patterns detected!\x1b[0m');
    if (shouldGenerateTodo) generateTodoFile({});
  } else {
    console.log(`\x1b[31m✖ ${totalViolations} anti-patterns detected:\x1b[0m\n`);
    for (const [file, violations] of Object.entries(allViolations)) {
      console.log(`\x1b[36m${file}\x1b[0m`);
      violations.forEach(v => {
        console.log(`  \x1b[90mLine ${v.line}:\x1b[0m [${v.pattern}] \x1b[33m${v.value}\x1b[0m - ${v.message}`);
      });
      console.log();
    }
    if (shouldGenerateTodo) generateTodoFile(allViolations);
    process.exit(1);
  }
}

runAudit();
