import assert from 'assert';

async function runTests() {
  const { checkContent } = await import('./detect-antipatterns.mjs');

  console.log('Running Audit Tool Tests...');

  // TSX Tests
  console.log('- should detect raw hex colors in TSX');
  const tsxHex = checkContent('<div className="bg-[#ff0000]">Hello</div>');
  assert(tsxHex.some(v => v.pattern === 'Raw Hex Color'));

  console.log('- should detect arbitrary values in TSX');
  const tsxArb = checkContent('<div className="w-[100px]">Hello</div>');
  assert(tsxArb.some(v => v.pattern === 'Arbitrary Value'));

  // CSS Tests
  console.log('- should detect raw hex colors in CSS');
  const cssHex = checkContent('.my-class { color: #ff0000; }', 'test.css');
  assert(cssHex.some(v => v.pattern === 'Raw Hex Color (CSS)'));

  console.log('- should detect hardcoded pixel values in CSS');
  const cssPx = checkContent('.my-class { padding: 13px; }', 'test.css');
  assert(cssPx.some(v => v.pattern === 'Hardcoded Pixel Value (CSS)'));

  console.log('- should detect Tailwind anti-patterns in @apply');
  const cssApply = checkContent('.my-class { @apply bg-[#ff0000] p-[13px]; }');
  assert(cssApply.some(v => v.pattern === 'Raw Hex Color'));
  assert(cssApply.some(v => v.pattern === 'Arbitrary Value'));

  console.log('- should detect multi-line @apply declarations');
  const cssMultiApply = checkContent('.my-class {\n  @apply\n    bg-[#ff0000]\n    p-[13px];\n}');
  assert(cssMultiApply.some(v => v.pattern === 'Raw Hex Color'));
  assert(cssMultiApply.some(v => v.pattern === 'Arbitrary Value'));

  // False Positive Tests
  console.log('- should NOT detect ID selectors as raw hex colors');
  const cssIdSelector = checkContent('#header { color: red; }', 'test.css');
  assert(!cssIdSelector.some(v => v.pattern === 'Raw Hex Color (CSS)'));

  console.log('- should NOT detect hex colors in comments');
  const cssComment = checkContent('/* Fix for issue #123456 */', 'test.css');
  assert(!cssComment.some(v => v.pattern === 'Raw Hex Color (CSS)'));

  // Ignore Tests
  console.log('- should skip files with // impeccable-ignore-file');
  const ignoreFile = checkContent('// impeccable-ignore-file\n.my-class { color: #ff0000; }', 'test.css');
  assert.strictEqual(ignoreFile.length, 0);

  console.log('- should skip files with /* impeccable-ignore-file */');
  const ignoreFileCss = checkContent('/* impeccable-ignore-file */\n.my-class { color: #ff0000; }', 'test.css');
  assert.strictEqual(ignoreFileCss.length, 0);

  console.log('- should skip lines with // impeccable-ignore');
  const ignoreLine = checkContent('.my-class { color: #ff0000; } // impeccable-ignore', 'test.css');
  assert.strictEqual(ignoreLine.length, 0);

  console.log('- should skip lines with /* impeccable-ignore */');
  const ignoreLineCss = checkContent('.my-class { color: #ff0000; } /* impeccable-ignore */', 'test.css');
  assert.strictEqual(ignoreLineCss.length, 0);

  // .npmrc Tests
  console.log('- should detect forbidden use-node-version in .npmrc');
  const npmrcForbidden = checkContent('use-node-version=true', '.npmrc');
  assert(npmrcForbidden.some(v => v.pattern === 'Forbidden .npmrc property'));

  console.log('All Audit Tool Tests Passed!');
}

runTests().catch(err => {
  console.error('Test Failed:', err);
  process.exit(1);
});
