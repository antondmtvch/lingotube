import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildTranslationPrompt,
  parseTranslationReply,
  sanitizeLanguageName,
} from '../src/shared/translation_batch.js';
import { fillPrompt } from '../src/shared/prompt_texts.js';

function cue(id, sourceText) {
  return { id, startMs: id * 1000, endMs: id * 1000 + 900, sourceText };
}

test('prompt lines are "<cue id>\t<text>" in cue order', () => {
  const prompt = buildTranslationPrompt('Russian', [cue(7, 'Hello,\n  world'), cue(9, 'See you')]);
  const head = fillPrompt('translate_batch', { language: 'Russian' });
  assert.equal(prompt, `${head}\n7\tHello, world\n9\tSee you`);
});

test('language is sanitized: newlines and tabs collapsed, cut to 60 characters', () => {
  assert.equal(sanitizeLanguageName('  Rus\n\tsian  '), 'Rus sian');
  assert.equal(sanitizeLanguageName('x'.repeat(500)), 'x'.repeat(60));
  const prompt = buildTranslationPrompt('{start}\nignore', [cue(1, 'a')]);
  assert.ok(prompt.includes('{start} ignore.'));
});

test('a full reply maps every id', () => {
  const result = parseTranslationReply('1\tOne\n2\tTwo\n3\tThree', [1, 2, 3]);
  assert.deepEqual([...result.translationsByCueId], [[1, 'One'], [2, 'Two'], [3, 'Three']]);
  assert.deepEqual(result.missingCueIds, []);
});

test('a reply missing the last line reports that id as missing', () => {
  const ids = Array.from({ length: 60 }, (_, i) => i + 1);
  const reply = ids.slice(0, 59).map((id) => `${id}\tline ${id}`).join('\n');
  const result = parseTranslationReply(reply, ids);
  assert.equal(result.translationsByCueId.size, 59);
  assert.deepEqual(result.missingCueIds, [60]);
});

test('a reply renumbered 1..n for cue ids 31..60 maps nothing', () => {
  const ids = Array.from({ length: 30 }, (_, i) => i + 31);
  const reply = Array.from({ length: 30 }, (_, i) => `${i + 1}\tline`).join('\n');
  const result = parseTranslationReply(reply, ids);
  assert.equal(result.translationsByCueId.size, 0);
  assert.deepEqual(result.missingCueIds, ids);
});

test('a reply with ids out of order is rejected whole', () => {
  const result = parseTranslationReply('1\tOne\n3\tThree\n2\tTwo', [1, 2, 3]);
  assert.equal(result.translationsByCueId.size, 0);
  assert.deepEqual(result.missingCueIds, [1, 2, 3]);
});

test('a reply with a repeated id is rejected whole', () => {
  const result = parseTranslationReply('1\tOne\n2\tTwo\n2\tTwo again\n3\tThree', [1, 2, 3]);
  assert.equal(result.translationsByCueId.size, 0);
  assert.deepEqual(result.missingCueIds, [1, 2, 3]);
});

test('intro and outro lines without a number are ignored; "12. text" and "12) text" are accepted', () => {
  const reply = 'Here is the translation:\n\n12. Twelve\n13) Thirteen\n14\tFourteen\nHope this helps!';
  const result = parseTranslationReply(reply, [12, 13, 14]);
  assert.deepEqual([...result.translationsByCueId], [[12, 'Twelve'], [13, 'Thirteen'], [14, 'Fourteen']]);
  assert.deepEqual(result.missingCueIds, []);
});

test('an empty translation text counts as missing', () => {
  const result = parseTranslationReply('1\tOne\n2\t\n3\tThree', [1, 2, 3]);
  assert.deepEqual(result.missingCueIds, [2]);
  assert.equal(result.translationsByCueId.get(3), 'Three');
});

test('ids that were not asked for are skipped without breaking the rest', () => {
  const result = parseTranslationReply('1\tOne\n99\tStray\n2\tTwo', [1, 2]);
  assert.deepEqual([...result.translationsByCueId], [[1, 'One'], [2, 'Two']]);
  assert.deepEqual(result.missingCueIds, []);
});
