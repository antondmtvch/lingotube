import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { PROMPT_TEXTS, PROMPT_VERSION, fillPrompt } from '../src/shared/prompt_texts.js';

/** Reads a prompt file of the Python package. */
function readPackagePrompt(name) {
  const url = new URL(`../../src/lingotube/prompts/${name}.v${PROMPT_VERSION}.txt`, import.meta.url);
  return readFileSync(fileURLToPath(url), 'utf8');
}

test('prompt copies equal the Python package files byte for byte', () => {
  for (const name of ['translate_batch', 'transcript_translated']) {
    assert.equal(PROMPT_TEXTS[name], readPackagePrompt(name), name);
  }
});

test('a language named "{start}" is inserted literally and not expanded again', () => {
  const filled = fillPrompt('transcript_translated', { start: 'S', end: 'E', language: '{start}' });
  assert.ok(filled.includes('на язык: {start}.'));
  assert.equal(filled.includes('{language}'), false);
});

test('a missing variable throws', () => {
  assert.throws(() => fillPrompt('translate_batch', {}), /language/);
});
