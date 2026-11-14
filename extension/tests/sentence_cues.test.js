import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildCues, DEFAULT_CUE_RULES, CUE_RULES_VERSION } from '../src/shared/sentence_cues.js';

/** Builds consecutive words, one every `stepMs`, each lasting `stepMs`. */
function wordsFromText(text, { startMs = 0, stepMs = 300 } = {}) {
  return text.split(' ').map((word, index) => ({
    text: word,
    startMs: startMs + index * stepMs,
    endMs: startMs + (index + 1) * stepMs,
  }));
}

test('rules version and defaults are fixed', () => {
  assert.equal(CUE_RULES_VERSION, '1');
  assert.deepEqual(DEFAULT_CUE_RULES, { maxChars: 84, maxDurationMs: 7000, pauseMs: 700 });
});

test('punctuation ends a cue', () => {
  const cues = buildCues(wordsFromText('speed it up. We will cover'));
  assert.deepEqual(
    cues.map((cue) => cue.sourceText),
    ['speed it up.', 'We will cover'],
  );
});

test('closing quotes after the sentence end stay in the cue', () => {
  const cues = buildCues(wordsFromText('He said "stop." Then left'));
  assert.deepEqual(
    cues.map((cue) => cue.sourceText),
    ['He said "stop."', 'Then left'],
  );
});

test('a pause of 700 ms ends a cue when there is no punctuation', () => {
  const first = wordsFromText('ты что глухой');
  const second = wordsFromText('и снято', { startMs: first[2].endMs + 900 });
  const cues = buildCues([...first, ...second]);
  assert.deepEqual(
    cues.map((cue) => cue.sourceText),
    ['ты что глухой', 'и снято'],
  );
});

test('a long sentence is split at a comma past the midpoint', () => {
  const text = 'one two three four five six seven eight nine, ten eleven twelve thirteen fourteen fifteen sixteen';
  const cues = buildCues(wordsFromText(text), { maxChars: 60, maxDurationMs: 100000, pauseMs: 700 });
  assert.equal(cues[0].sourceText, 'one two three four five six seven eight nine,');
  assert.ok(cues.every((cue) => cue.sourceText.length <= 60));
});

test('a comma before the midpoint is ignored and the cue splits before the overflowing word', () => {
  const text = 'a, bbb ccc ddd eee fff ggg hhh iii jjj kkk';
  const cues = buildCues(wordsFromText(text), { maxChars: 30, maxDurationMs: 100000, pauseMs: 700 });
  assert.ok(cues[0].sourceText.length > 'a,'.length);
  assert.ok(cues.every((cue) => cue.sourceText.length <= 30));
});

test('a long run without commas is split before the overflowing word', () => {
  const text = Array.from({ length: 60 }, (_, index) => `word${index}`).join(' ');
  const cues = buildCues(wordsFromText(text));
  assert.ok(cues.length > 1);
  assert.ok(cues.every((cue) => cue.sourceText.length <= DEFAULT_CUE_RULES.maxChars));
  assert.equal(cues.map((cue) => cue.sourceText).join(' '), text);
});

test('no cue is longer than 7000 ms', () => {
  const cues = buildCues(wordsFromText('a b c d e f g h i j k l m n o p q r s t', { stepMs: 1000 }));
  assert.ok(cues.length > 1);
  assert.ok(cues.every((cue) => cue.endMs - cue.startMs <= DEFAULT_CUE_RULES.maxDurationMs));
});

test('cue end never passes the next cue start; ids are 1..n', () => {
  const words = [
    { text: 'one.', startMs: 0, endMs: 2000 },
    { text: 'two.', startMs: 500, endMs: 900 },
    { text: 'three', startMs: 1000, endMs: 1200 },
  ];
  const cues = buildCues(words);
  assert.deepEqual(
    cues.map((cue) => cue.id),
    [1, 2, 3],
  );
  assert.equal(cues[0].endMs, 500);
  for (let index = 1; index < cues.length; index += 1) {
    assert.ok(cues[index - 1].endMs <= cues[index].startMs);
  }
  assert.equal(cues[2].endMs, 1200);
});

test('a single word longer than maxChars is kept whole as its own cue', () => {
  const longWord = 'x'.repeat(100);
  const cues = buildCues([
    { text: 'a', startMs: 0, endMs: 100 },
    { text: longWord, startMs: 100, endMs: 200 },
    { text: 'b', startMs: 200, endMs: 300 },
  ]);
  assert.deepEqual(
    cues.map((cue) => cue.sourceText),
    ['a', longWord, 'b'],
  );
});

test('empty input gives no cues', () => {
  assert.deepEqual(buildCues([]), []);
});
