import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { timedWordsFromJson3 } from '../src/shared/json3_captions.js';

const readFixture = (name) =>
  JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), 'utf8'));

test('asr words get start = tStartMs + tOffsetMs and end = next word start', () => {
  const words = timedWordsFromJson3(readFixture('captions_asr.json3.json'));
  assert.deepEqual(words[0], { text: 'A', startMs: 100, endMs: 400 });
  assert.deepEqual(words[1], { text: 'complete', startMs: 400, endMs: 1000 });
});

test('word duration is capped at 1500 ms before a pause', () => {
  const words = timedWordsFromJson3(readFixture('captions_asr.json3.json'));
  assert.deepEqual(words[4], { text: 'this.', startMs: 2510, endMs: 4010 });
  assert.deepEqual(words[5], { text: '[music]', startMs: 9000, endMs: 10500 });
});

test('newline-only and seg-less events are skipped', () => {
  const words = timedWordsFromJson3(readFixture('captions_asr.json3.json'));
  assert.equal(words.length, 6);
});

test('a manual event becomes one TimedWord with the whole line', () => {
  const words = timedWordsFromJson3(readFixture('captions_manual.json3.json'));
  assert.deepEqual(words, [
    { text: 'Hello there.', startMs: 1000, endMs: 3500 },
    { text: 'How are you?', startMs: 4000, endMs: 6000 },
  ]);
});

test('garbage input gives an empty list', () => {
  assert.deepEqual(timedWordsFromJson3({}), []);
  assert.deepEqual(timedWordsFromJson3({ events: 'x' }), []);
  assert.deepEqual(timedWordsFromJson3(null), []);
});
