import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const CYRILLIC_LETTER = /[Ѐ-ӿ]/u;

/** Source code without block and line comments. String contents are kept. */
function sourceWithoutComments(relativePath) {
  const source = readFileSync(new URL(relativePath, import.meta.url), 'utf8');
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/\s\/\/.*$/gm, '');
}

for (const file of ['../src/page/player_controls.js', '../src/page/overlay_view.js']) {
  test(`${file} has no hardcoded Cyrillic text outside comments`, () => {
    const codeLines = sourceWithoutComments(file).split('\n');
    const offending = codeLines.filter((line) => CYRILLIC_LETTER.test(line));
    assert.deepEqual(offending, []);
  });
}
