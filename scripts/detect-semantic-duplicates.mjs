#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';

const ROOT = process.cwd();
const SRC_DIR = path.join(ROOT, 'src');
const OUTPUT_DIR = path.join(ROOT, 'artifacts', 'semantic-duplicates');
const REPORT_PATH = path.join(OUTPUT_DIR, 'report.md');
const JSON_PATH = path.join(OUTPUT_DIR, 'report.json');
const SCORE_THRESHOLD = 55;
const MAX_REPORTED_PAIRS = 250;

const IGNORED_SEGMENTS = new Set(['node_modules', 'dist', 'coverage', 'playwright-report', 'test-results', 'layouts', 'ui', 'editorial']);
const JSX_EXTENSIONS = new Set(['.tsx', '.jsx']);
const ANALYZED_EXTENSIONS = new Set(['.tsx', '.ts', '.jsx', '.js']);
const UTILITY_CALL_ALLOWLIST = new Set([
  'Array', 'Boolean', 'Date', 'Error', 'Map', 'Number', 'Object', 'Promise', 'RegExp', 'Set', 'String',
  'console', 'JSON', 'Math', 'Intl', 'parseFloat', 'parseInt', 'encodeURIComponent', 'decodeURIComponent',
]);

function walk(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  return entries.flatMap((entry) => {
    if (entry.name.startsWith('.') || IGNORED_SEGMENTS.has(entry.name)) {
      return [];
    }

    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      return walk(fullPath);
    }

    if (!ANALYZED_EXTENSIONS.has(path.extname(entry.name))) {
      return [];
    }

    return [fullPath];
  });
}

function toRepoPath(filePath) {
  return path.relative(ROOT, filePath).split(path.sep).join('/');
}

function getNameText(name) {
  if (ts.isIdentifier(name)) {
    return name.text;
  }

  if (ts.isJsxNamespacedName?.(name)) {
    return `${name.namespace.text}:${name.name.text}`;
  }

  if (ts.isPropertyAccessExpression(name)) {
    return `${getNameText(name.expression)}.${name.name.text}`;
  }

  return 'unknown';
}

function normalizeTagName(name) {
  const tag = getNameText(name);
  if (/^[a-z]/.test(tag)) {
    return tag;
  }

  if (tag.includes('.')) {
    return tag.split('.').map((segment) => (segment === 'motion' ? 'motion' : 'Component')).join('.');
  }

  return 'Component';
}

function getJsxChildren(node) {
  if (ts.isJsxElement(node)) {
    return node.children;
  }

  if (ts.isJsxFragment(node)) {
    return node.children;
  }

  return [];
}

function buildJsxTree(node) {
  if (ts.isJsxSelfClosingElement(node)) {
    return { tag: normalizeTagName(node.tagName), rawTag: getNameText(node.tagName), children: [] };
  }

  if (ts.isJsxElement(node)) {
    const children = Array.from(getJsxChildren(node))
      .map(buildJsxTree)
      .filter(Boolean);
    return { tag: normalizeTagName(node.openingElement.tagName), rawTag: getNameText(node.openingElement.tagName), children };
  }

  if (ts.isJsxFragment(node)) {
    const children = Array.from(getJsxChildren(node))
      .map(buildJsxTree)
      .filter(Boolean);
    return { tag: 'Fragment', rawTag: 'Fragment', children };
  }

  if (ts.isJsxExpression(node) && node.expression) {
    if (ts.isJsxElement(node.expression) || ts.isJsxSelfClosingElement(node.expression) || ts.isJsxFragment(node.expression)) {
      return buildJsxTree(node.expression);
    }

    return { tag: 'expression', rawTag: 'expression', children: [] };
  }

  if (ts.isJsxText(node)) {
    return node.text.trim() ? { tag: 'text', rawTag: 'text', children: [] } : null;
  }

  return null;
}

function collectTags(tree, predicate, results = new Set()) {
  if (!tree) {
    return results;
  }

  const tag = tree.rawTag ?? tree.tag;
  if (predicate(tag)) {
    results.add(tag);
  }

  tree.children.forEach((child) => collectTags(child, predicate, results));
  return results;
}

function collectSubtreeSignatures(tree, signatures = new Map()) {
  if (!tree) {
    return signatures;
  }

  const signature = `${tree.tag}(${tree.children.map((child) => collectSubtreeSignatures(child, signatures).currentSignature).join(',')})`;
  const display = `${tree.tag}${tree.children.length > 0 ? ` → ${tree.children.map((child) => child.tag).join(' → ')}` : ''}`;
  const count = signatures.get(signature) ?? { signature, display, count: 0 };
  count.count += 1;
  signatures.set(signature, count);
  signatures.currentSignature = signature;
  return signatures;
}

function flattenTree(tree, includeDepth = false, depth = 0) {
  if (!tree) {
    return [];
  }

  const current = includeDepth ? `${depth}:${tree.tag}` : tree.tag;
  return [current, ...tree.children.flatMap((child) => flattenTree(child, includeDepth, depth + 1))];
}

function treeDepth(tree) {
  if (!tree || tree.children.length === 0) {
    return tree ? 1 : 0;
  }

  return 1 + Math.max(...tree.children.map(treeDepth));
}

function extractStringLiteral(node) {
  if (!node) {
    return null;
  }

  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    return node.text;
  }

  if (ts.isJsxExpression(node) && node.expression) {
    return extractStringLiteral(node.expression);
  }

  return null;
}

function attributeName(attribute) {
  return ts.isIdentifier(attribute.name) ? attribute.name.text : attribute.name.getText();
}

function collectImports(sourceFile) {
  const imports = new Set();
  sourceFile.statements.forEach((statement) => {
    if (!ts.isImportDeclaration(statement) || !statement.importClause) {
      return;
    }

    const specifier = statement.moduleSpecifier.getText(sourceFile).replaceAll(/["']/g, '');
    if (statement.importClause.name) {
      imports.add(statement.importClause.name.text);
    }

    const bindings = statement.importClause.namedBindings;
    if (bindings && ts.isNamedImports(bindings)) {
      bindings.elements.forEach((element) => imports.add(element.name.text));
    }

    if (bindings && ts.isNamespaceImport(bindings)) {
      imports.add(bindings.name.text);
    }

    imports.add(`module:${specifier}`);
  });
  return imports;
}

function addClassValue(classValue, classTokens, classPatterns) {
  const normalized = classValue.split(/\s+/).filter(Boolean).join(' ');
  if (!normalized) {
    return;
  }

  classPatterns.add(normalized);
  normalized.split(' ').forEach((token) => classTokens.add(token));
}

function hasJsx(node) {
  let found = false;
  function visit(child) {
    if (found) {
      return;
    }
    if (ts.isJsxElement(child) || ts.isJsxSelfClosingElement(child) || ts.isJsxFragment(child)) {
      found = true;
      return;
    }
    ts.forEachChild(child, visit);
  }
  visit(node);
  return found;
}

function findReturnJsx(node) {
  if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node) || ts.isJsxFragment(node)) {
    return node;
  }

  if (ts.isParenthesizedExpression(node)) {
    return findReturnJsx(node.expression);
  }

  if (ts.isReturnStatement(node) && node.expression) {
    return findReturnJsx(node.expression);
  }

  let result = null;
  function visit(child) {
    if (result) {
      return;
    }
    if (ts.isReturnStatement(child) && child.expression) {
      result = findReturnJsx(child.expression);
      return;
    }
    ts.forEachChild(child, visit);
  }
  ts.forEachChild(node, visit);
  return result;
}

function isComponentLikeName(name) {
  return /^[A-Z]/.test(name);
}

function componentNameFromStatement(statement) {
  if (ts.isFunctionDeclaration(statement) && statement.name && isComponentLikeName(statement.name.text) && hasJsx(statement)) {
    return statement.name.text;
  }

  if (ts.isVariableStatement(statement)) {
    for (const declaration of statement.declarationList.declarations) {
      if (!ts.isIdentifier(declaration.name) || !declaration.initializer || !isComponentLikeName(declaration.name.text)) {
        continue;
      }

      if ((ts.isArrowFunction(declaration.initializer) || ts.isFunctionExpression(declaration.initializer)) && hasJsx(declaration.initializer)) {
        return declaration.name.text;
      }
    }
  }

  return null;
}

function collectCallsAndClasses(node, sourceFile, classTokens, classPatterns, hooks, utilities) {
  function visit(child) {
    if (ts.isJsxAttribute(child) && attributeName(child) === 'className') {
      const literal = extractStringLiteral(child.initializer);
      if (literal) {
        addClassValue(literal, classTokens, classPatterns);
      }
    }

    if (ts.isCallExpression(child)) {
      const expression = child.expression;
      const callName = expression.getText(sourceFile).split('.')[0] ?? expression.getText(sourceFile);
      if (/^use[A-Z0-9]/.test(callName)) {
        hooks.add(callName);
      } else if (/^[A-Za-z_$][\w$]*$/.test(callName) && !UTILITY_CALL_ALLOWLIST.has(callName)) {
        utilities.add(callName);
      } else if (expression.getText(sourceFile).includes('toLocaleDateString')) {
        utilities.add('toLocaleDateString');
      }
    }

    if (ts.isNewExpression(child)) {
      const name = child.expression.getText(sourceFile);
      if (name === 'Date') {
        utilities.add('new Date');
      }
    }

    ts.forEachChild(child, visit);
  }

  visit(node);
}

function analyzeFile(filePath) {
  const code = fs.readFileSync(filePath, 'utf8');
  const sourceFile = ts.createSourceFile(filePath, code, ts.ScriptTarget.Latest, true, filePath.endsWith('.tsx') || filePath.endsWith('.jsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const repoPath = toRepoPath(filePath);
  const imports = collectImports(sourceFile);
  const components = [];
  const functions = [];

  sourceFile.statements.forEach((statement) => {
    const name = componentNameFromStatement(statement);
    if (name) {
      const jsxRoot = findReturnJsx(statement);
      const tree = jsxRoot ? buildJsxTree(jsxRoot) : null;
      const classTokens = new Set();
      const classPatterns = new Set();
      const hooks = new Set();
      const utilities = new Set();
      collectCallsAndClasses(statement, sourceFile, classTokens, classPatterns, hooks, utilities);
      const structure = flattenTree(tree, false);
      const hierarchy = flattenTree(tree, true);
      const componentTags = [...collectTags(tree, (tag) => /^[A-Z]/.test(tag) || tag.includes('.'))].sort();
      const intrinsicTags = [...collectTags(tree, (tag) => /^[a-z]/.test(tag))].sort();
      const subtreeEntries = tree ? [...collectSubtreeSignatures(tree).values()].filter((entry) => entry.signature) : [];
      components.push({
        name,
        file: repoPath,
        root: tree?.tag ?? 'unknown',
        depth: treeDepth(tree),
        structure,
        hierarchy,
        structureHash: structure.join('>'),
        hierarchyHash: hierarchy.join('>'),
        classTokens: [...classTokens].sort(),
        classPatterns: [...classPatterns].sort(),
        imports: [...imports].sort(),
        componentTags,
        intrinsicTags,
        subtrees: subtreeEntries.map((entry) => ({ signature: entry.signature, display: entry.display, count: entry.count })),
        hooks: [...hooks].sort(),
        utilities: [...utilities].sort(),
      });
    }

    const functionName = getFunctionName(statement);
    if (functionName) {
      const calls = new Set();
      const dateSignals = new Set();
      collectFunctionCalls(statement, sourceFile, calls, dateSignals);
      if (calls.size > 0 || dateSignals.size > 0) {
        functions.push({
          name: functionName,
          file: repoPath,
          calls: [...calls].sort(),
          dateSignals: [...dateSignals].sort(),
        });
      }
    }
  });

  return { components, functions };
}

function getFunctionName(statement) {
  if (ts.isFunctionDeclaration(statement) && statement.name) {
    return statement.name.text;
  }

  if (ts.isVariableStatement(statement)) {
    for (const declaration of statement.declarationList.declarations) {
      if (ts.isIdentifier(declaration.name) && declaration.initializer) {
        if (ts.isArrowFunction(declaration.initializer) || ts.isFunctionExpression(declaration.initializer)) {
          return declaration.name.text;
        }
      }
    }
  }

  return null;
}

function collectFunctionCalls(node, sourceFile, calls, dateSignals) {
  function visit(child) {
    if (ts.isCallExpression(child)) {
      const text = child.expression.getText(sourceFile);
      const base = text.split('.')[0] ?? text;
      calls.add(text);
      if (text.includes('toLocaleDateString') || text.includes('format') || text.includes('parseISO')) {
        dateSignals.add(text);
      }
      if (base === 'Date' || text.includes('Date')) {
        dateSignals.add(text);
      }
    }

    if (ts.isNewExpression(child)) {
      const text = child.expression.getText(sourceFile);
      calls.add(`new ${text}`);
      if (text === 'Date') {
        dateSignals.add('new Date');
      }
    }

    ts.forEachChild(child, visit);
  }

  visit(node);
}

function jaccard(left, right) {
  const leftSet = new Set(left);
  const rightSet = new Set(right);
  if (leftSet.size === 0 && rightSet.size === 0) {
    return 1;
  }

  const intersection = [...leftSet].filter((item) => rightSet.has(item)).length;
  const union = new Set([...leftSet, ...rightSet]).size;
  return union === 0 ? 0 : intersection / union;
}

function similarity(left, right) {
  const structure = jaccard(left.structure, right.structure);
  const hierarchy = jaccard(left.hierarchy, right.hierarchy);
  const classes = jaccard(left.classTokens, right.classTokens);
  const imports = jaccard(left.componentTags, right.componentTags);
  const hooks = jaccard(left.hooks, right.hooks);
  const utilities = jaccard(left.utilities, right.utilities);

  const score = (structure * 40) + (hierarchy * 20) + (classes * 15) + (imports * 10) + (hooks * 10) + (utilities * 5);
  return {
    score: Math.round(score),
    metrics: {
      structure: Math.round(structure * 100),
      hierarchy: Math.round(hierarchy * 100),
      classNames: Math.round(classes * 100),
      componentUsage: Math.round(imports * 100),
      hooks: Math.round(hooks * 100),
      utilities: Math.round(utilities * 100),
    },
  };
}

function bucketForScore(score) {
  if (score >= 90) return 'Definitely duplicate';
  if (score >= 75) return 'Likely duplicate';
  if (score >= 60) return 'Review manually';
  return 'Different component';
}

function pairComponents(components) {
  const pairs = [];
  for (let i = 0; i < components.length; i += 1) {
    for (let j = i + 1; j < components.length; j += 1) {
      const left = components[i];
      const right = components[j];
      if (left.file === right.file && left.name === right.name) {
        continue;
      }
      const result = similarity(left, right);
      if (result.score >= SCORE_THRESHOLD) {
        pairs.push({
          score: result.score,
          bucket: bucketForScore(result.score),
          metrics: result.metrics,
          left: componentSummary(left),
          right: componentSummary(right),
        });
      }
    }
  }

  return pairs.sort((left, right) => right.score - left.score || left.left.file.localeCompare(right.left.file));
}

function componentSummary(component) {
  return {
    name: component.name,
    file: component.file,
    root: component.root,
    depth: component.depth,
    structureHash: component.structureHash,
    classPatterns: component.classPatterns,
    hooks: component.hooks,
    utilities: component.utilities,
  };
}

function repeatedClassPatterns(components) {
  const patternFiles = new Map();
  components.forEach((component) => {
    component.classPatterns.forEach((pattern) => {
      if (!patternFiles.has(pattern)) {
        patternFiles.set(pattern, new Set());
      }
      patternFiles.get(pattern).add(`${component.file}#${component.name}`);
    });
  });

  return [...patternFiles.entries()]
    .map(([pattern, owners]) => ({ pattern, count: owners.size, owners: [...owners].sort() }))
    .filter((entry) => entry.count >= 3 || (entry.count >= 2 && entry.pattern.split(' ').length >= 4))
    .sort((left, right) => right.count - left.count || right.pattern.length - left.pattern.length);
}

function duplicateFunctionSignals(functions) {
  const groups = new Map();
  functions.forEach((fn) => {
    if (fn.dateSignals.length === 0) {
      return;
    }
    const key = fn.dateSignals.join('|');
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key).push(fn);
  });

  return [...groups.entries()]
    .map(([signature, items]) => ({ signature, items }))
    .filter((group) => group.items.length > 1)
    .sort((left, right) => right.items.length - left.items.length);
}


function splitWords(name) {
  return name
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[^A-Za-z0-9]+/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
}

const ROLE_TOKENS = [
  'Hero', 'Header', 'Card', 'Grid', 'Sidebar', 'Newsletter', 'CTA', 'Button', 'Badge', 'Skeleton',
  'Layout', 'Tool', 'Page', 'Chart', 'Form', 'Navigation', 'Content', 'Preview', 'Image', 'Detail',
  'Feed', 'List', 'Search', 'Disclosure', 'Callout', 'Selector', 'Table', 'Stats', 'Export',
];

function roleGroups(components) {
  return ROLE_TOKENS.map((role) => {
    const members = components.filter((component) => {
      const words = splitWords(`${component.name} ${component.file}`);
      return words.some((word) => word.toLowerCase() === role.toLowerCase());
    });
    return { role, members: members.map(componentSummary).sort((left, right) => left.file.localeCompare(right.file)) };
  }).filter((group) => group.members.length >= 2);
}

function exactStructureGroups(components) {
  const groups = new Map();
  components.forEach((component) => {
    if (!component.structureHash || component.structureHash === 'unknown' || component.structureHash.split('>').length < 2) {
      return;
    }
    if (!groups.has(component.structureHash)) {
      groups.set(component.structureHash, []);
    }
    groups.get(component.structureHash).push(componentSummary(component));
  });

  return [...groups.entries()]
    .map(([signature, members]) => ({ signature, members }))
    .filter((group) => group.members.length >= 2)
    .sort((left, right) => right.members.length - left.members.length || left.signature.localeCompare(right.signature));
}

function repeatedSubtreePatterns(components) {
  const groups = new Map();
  components.forEach((component) => {
    component.subtrees.forEach((subtree) => {
      if (subtree.signature.length < 18 || !subtree.signature.includes(',')) {
        return;
      }
      if (!groups.has(subtree.signature)) {
        groups.set(subtree.signature, { signature: subtree.signature, display: subtree.display, owners: new Set(), occurrences: 0 });
      }
      const group = groups.get(subtree.signature);
      group.owners.add(`${component.file}#${component.name}`);
      group.occurrences += subtree.count;
    });
  });

  return [...groups.values()]
    .map((group) => ({ ...group, owners: [...group.owners].sort() }))
    .filter((group) => group.owners.length >= 3 || group.occurrences >= 5)
    .sort((left, right) => right.owners.length - left.owners.length || right.occurrences - left.occurrences);
}

function renderRoleGroups(groups) {
  if (groups.length === 0) {
    return 'No semantic role groups were detected.';
  }

  return groups.map((group) => [
    `### ${group.role} components (${group.members.length})`,
    '',
    ...group.members.map((member) => `- ${member.file}#${member.name}`),
    '',
  ].join('\n')).join('\n');
}

function renderExactStructureGroups(groups) {
  if (groups.length === 0) {
    return 'No exact structural groups were detected.';
  }

  return groups.slice(0, 40).map((group) => [
    `### ${group.members.length} components with \`${group.signature}\``,
    '',
    ...group.members.map((member) => `- ${member.file}#${member.name}`),
    '',
  ].join('\n')).join('\n');
}

function renderSubtreePatterns(patterns) {
  if (patterns.length === 0) {
    return 'No repeated JSX subtree patterns were detected.';
  }

  return patterns.slice(0, 40).map((pattern) => [
    `### ${pattern.display}`,
    '',
    `- Owners: ${pattern.owners.length}`,
    `- Occurrences: ${pattern.occurrences}`,
    ...pattern.owners.slice(0, 12).map((owner) => `- ${owner}`),
    '',
  ].join('\n')).join('\n');
}

function renderInventory(files, components) {
  const directories = [...new Set(files.map((file) => path.dirname(toRepoPath(file))))].sort();
  const componentLines = components
    .sort((left, right) => left.file.localeCompare(right.file) || left.name.localeCompare(right.name))
    .map((component) => `- ${component.file}#${component.name}`);

  return [
    '## Component Inventory',
    '',
    '### Source Directories',
    '',
    ...directories.map((dir) => `- ${dir}`),
    '',
    '### TSX Components',
    '',
    ...componentLines,
  ].join('\n');
}

function renderReport({ files, components, pairs, classPatterns, functionGroups, semanticRoleGroups, structuralGroups, subtreePatterns }) {
  const generatedAt = new Date().toISOString();
  const pairLines = pairs.slice(0, MAX_REPORTED_PAIRS).flatMap((pair, index) => [
    `### ${index + 1}. ${pair.left.name} ↔ ${pair.right.name}`,
    '',
    `- Similarity: **${pair.score}%** (${pair.bucket})`,
    `- Files: \`${pair.left.file}\` and \`${pair.right.file}\``,
    `- Roots/depth: \`${pair.left.root}\`/${pair.left.depth} and \`${pair.right.root}\`/${pair.right.depth}`,
    `- Metrics: structure ${pair.metrics.structure}%, hierarchy ${pair.metrics.hierarchy}%, class names ${pair.metrics.classNames}%, component usage ${pair.metrics.componentUsage}%, hooks ${pair.metrics.hooks}%, utilities ${pair.metrics.utilities}%`,
    `- Recommendation: review whether these belong behind a shared primitive, composed component, or variant API.`,
    '',
  ]);

  const classLines = classPatterns.slice(0, 30).flatMap((entry) => [
    `### \`${entry.pattern}\``,
    '',
    `- Occurrences: ${entry.count}`,
    ...entry.owners.slice(0, 10).map((owner) => `- ${owner}`),
    '',
  ]);

  const functionLines = functionGroups.flatMap((group) => [
    `### ${group.signature}`,
    '',
    ...group.items.map((item) => `- ${item.file}#${item.name}`),
    '',
  ]);

  return [
    '# Semantic Duplicate Report',
    '',
    `Generated: ${generatedAt}`,
    '',
    'This report uses TypeScript AST traversal to fingerprint JSX structure, child hierarchy, className patterns, imported symbols, hook usage, and utility calls. Scores follow the project semantic-duplicate rubric: 90-100% definitely duplicate, 75-89% likely duplicate, 60-74% manual review.',
    '',
    renderInventory(files.filter((file) => JSX_EXTENSIONS.has(path.extname(file))), components),
    '',
    '## Semantic Role Groups',
    '',
    renderRoleGroups(semanticRoleGroups),
    '',
    '## Exact Structure Groups',
    '',
    renderExactStructureGroups(structuralGroups),
    '',
    '## Repeated JSX Subtree Patterns',
    '',
    renderSubtreePatterns(subtreePatterns),
    '',
    '## Candidate Duplicate Components',
    '',
    pairLines.length > 0 ? pairLines.join('\n') : 'No component pairs met the review threshold.',
    '',
    '## Repeated Class Patterns',
    '',
    classLines.length > 0 ? classLines.join('\n') : 'No repeated className patterns met the reporting threshold.',
    '',
    '## Duplicate Date/Formatting Logic Signals',
    '',
    functionLines.length > 0 ? functionLines.join('\n') : 'No repeated date/formatting function signatures were detected.',
    '',
  ].join('\n');
}

const files = walk(SRC_DIR);
const analyzed = files.map(analyzeFile);
const components = analyzed.flatMap((result) => result.components);
const functions = analyzed.flatMap((result) => result.functions);
const pairs = pairComponents(components);
const classPatterns = repeatedClassPatterns(components);
const functionGroups = duplicateFunctionSignals(functions);
const semanticRoleGroups = roleGroups(components);
const structuralGroups = exactStructureGroups(components);
const subtreePatterns = repeatedSubtreePatterns(components);
const report = renderReport({ files, components, pairs, classPatterns, functionGroups, semanticRoleGroups, structuralGroups, subtreePatterns });

fs.mkdirSync(OUTPUT_DIR, { recursive: true });
fs.writeFileSync(REPORT_PATH, report);
fs.writeFileSync(JSON_PATH, JSON.stringify({ components, pairs, classPatterns, functionGroups, semanticRoleGroups, structuralGroups, subtreePatterns }, null, 2));

console.log(`Semantic duplicate report written to ${toRepoPath(REPORT_PATH)}`);
console.log(`Components analyzed: ${components.length}`);
console.log(`Candidate duplicate pairs: ${pairs.length}`);
console.log(`Semantic role groups: ${semanticRoleGroups.length}`);
console.log(`Exact structure groups: ${structuralGroups.length}`);
console.log(`Repeated JSX subtree patterns: ${subtreePatterns.length}`);
console.log(`Repeated class patterns: ${classPatterns.length}`);
console.log(`Duplicate function signal groups: ${functionGroups.length}`);
