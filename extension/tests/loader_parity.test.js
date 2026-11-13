import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { STORAGE_CHANNEL } from '../src/shared/storage_messages.js';

const loaderText = readFileSync(new URL('../loader.js', import.meta.url), 'utf8');
const hostText = readFileSync(new URL('../src/content/storage_host.js', import.meta.url), 'utf8');
const messagesText = readFileSync(new URL('../src/shared/storage_messages.js', import.meta.url), 'utf8');

function normalizeWhitespace(text) {
  return text.replace(/\s+/g, ' ').trim();
}

/** Returns the source of `function name(...) { ... }` found by brace matching, without `export`. */
function extractFunctionSource(sourceText, functionName) {
  const start = sourceText.search(new RegExp(`function ${functionName}\(`));
  assert.ok(start >= 0, `function ${functionName} not found`);
  const bodyStart = sourceText.indexOf('{', sourceText.indexOf(')', start));
  let depth = 0;
  for (let index = bodyStart; index < sourceText.length; index += 1) {
    if (sourceText[index] === '{') depth += 1;
    if (sourceText[index] === '}') depth -= 1;
    if (depth === 0) return normalizeWhitespace(sourceText.slice(start, index + 1));
  }
  throw new Error(`unterminated function ${functionName}`);
}

test('loader.js is a classic script without import or export', () => {
  assert.doesNotMatch(loaderText, /^\s*(import|export)\s/m);
  assert.doesNotMatch(loaderText, /\bimport\s*\(/);
});

test('loader.js duplicates the channel constants of storage_messages.js', () => {
  assert.ok(loaderText.includes(`const STORAGE_CHANNEL = '${STORAGE_CHANNEL}';`));
  const operations = messagesText.match(/const STORAGE_OPERATIONS = (\[[^\]]*\]);/)[1];
  assert.ok(loaderText.includes(`const STORAGE_OPERATIONS = ${operations};`));
});

for (const functionName of ['isStorageRequest', 'createStorageResponse']) {
  test(`loader.js copy of ${functionName} matches storage_messages.js`, () => {
    assert.equal(extractFunctionSource(loaderText, functionName), extractFunctionSource(messagesText, functionName));
  });
}

test('loader.js copy of startStorageHost matches storage_host.js', () => {
  assert.equal(extractFunctionSource(loaderText, 'startStorageHost'), extractFunctionSource(hostText, 'startStorageHost'));
});
