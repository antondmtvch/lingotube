import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  formatPromptTime,
  parseTimestampedAnswer,
  withReadingTimeEnds,
} from '../src/shared/timestamped_transcript.js';

const line = (startMs, endMs, text) => ({ startMs, endMs, text });

test('(m:ss), (h:mm:ss) and (m:ss-m:ss) lines are parsed', () => {
  assert.deepEqual(parseTimestampedAnswer('(0:14) Всем привет, дорогие друзья.'), [
    line(14000, null, 'Всем привет, дорогие друзья.'),
  ]);
  assert.deepEqual(parseTimestampedAnswer('(1:00:00) x'), [line(3600000, null, 'x')]);
  assert.deepEqual(
    parseTimestampedAnswer('(0:02-0:04) Помогите!\n(0:04-0:07) Загоняем.\n(0:07-0:10) Вот и думайте.\n'),
    [line(2000, 4000, 'Помогите!'), line(4000, 7000, 'Загоняем.'), line(7000, 10000, 'Вот и думайте.')],
  );
  for (const [text, startMs, endMs] of [
    ['(1:02:03-1:02:07) x', 3723000, 3727000],
    ['[0:02 - 0:04] x', 2000, 4000],
    ['(0:02–0:04) x', 2000, 4000],
    ['(0:02—0:04) x', 2000, 4000],
    ['**(0:02-0:04)** x', 2000, 4000],
    ['- (0:02-0:04) x', 2000, 4000],
    ['(00:02-00:04) x', 2000, 4000],
    ['-  **(0:02-0:04)** x', 2000, 4000],
    ['(105:30) x', 6330000, null],
    ['(0:10-0:05) x', 10000, null],
    ['(5:25-5:25) x', 325000, 325000],
  ]) {
    assert.deepEqual(parseTimestampedAnswer(text), [line(startMs, endMs, 'x')], text);
  }
  for (const text of ['**(0:02) x**', '**(0:02)** x', '1. (0:02) x', '12) (0:02) x', '• (0:02) x', '– (0:02) x', '— (0:02) x', '*   (0:02) x']) {
    assert.deepEqual(parseTimestampedAnswer(text), [line(2000, null, 'x')], text);
  }
  assert.deepEqual(parseTimestampedAnswer('(0:05) [gasps] ох'), [line(5000, null, '[gasps] ох')]);
  assert.deepEqual(parseTimestampedAnswer('(0:02-0:04) a\r\n(0:04-0:06) b\r\n').map((cue) => cue.text), ['a', 'b']);
});

test('out-of-range timestamps are not timestamps; empty answers and empty texts give nothing', () => {
  for (const text of ['(0:75) x', '(1:99:99-0:01) x', '(1:60:00) x', '(0:02-0:99) x', 'Извините, я не могу помочь.', '', '(0:02-0:04)   ']) {
    assert.deepEqual(parseTimestampedAnswer(text), [], text);
  }
  assert.deepEqual(parseTimestampedAnswer('(0:02) a\n(0:75) b'), [line(2000, null, 'a (0:75) b')]);
});

test('intro before the first timestamp and outro after a blank line are dropped', () => {
  const answer = 'Вот расшифровка:\n\n(0:02) Раз\n(0:05) Два\n\nНадеюсь, это помогло!';
  assert.deepEqual(parseTimestampedAnswer(answer), [line(2000, null, 'Раз'), line(5000, null, 'Два')]);
});

test('a line without a timestamp joins the previous cue', () => {
  assert.equal(parseTimestampedAnswer('(0:02-0:04) Первая\nпродолжение\n(0:05-0:06) Вторая')[0].text, 'Первая продолжение');
  assert.deepEqual(parseTimestampedAnswer('(0:02) Раз\nНадеюсь'), [line(2000, null, 'Раз Надеюсь')]);
  assert.deepEqual(parseTimestampedAnswer('(0:02) see you at (0:30) ok\ncontinues (0:40) here'), [
    line(2000, null, 'see you at (0:30) ok continues (0:40) here'),
  ]);
});

test('of two lines with the same timestamp the second is kept', () => {
  assert.deepEqual(parseTimestampedAnswer('(0:02) Hello\n(0:02) Привет\n(0:05) Пока'), [
    line(2000, null, 'Привет'),
    line(5000, null, 'Пока'),
  ]);
  // Only pairs: of three identical timestamps the second and the third remain.
  assert.deepEqual(parseTimestampedAnswer('(0:02) a\n(0:02) b\n(0:02) c').map((cue) => cue.text), ['b', 'c']);
});

test('a long whitespace line is parsed quickly', () => {
  const startedAt = performance.now();
  assert.deepEqual(parseTimestampedAnswer(' '.repeat(100000) + 'x'), []);
  assert.deepEqual(parseTimestampedAnswer('- ' + ' '.repeat(100000) + 'x'), []);
  assert.equal(parseTimestampedAnswer('(0:01) a\n- ' + ' '.repeat(100000) + 'x')[0].startMs, 1000);
  assert.ok(performance.now() - startedAt < 500);
});

test('reading-time end: 1.5 s minimum, 7 s maximum, never past the next start', () => {
  const ends = withReadingTimeEnds(
    [
      line(0, null, 'ab'), // 2 chars → 1.5 s minimum
      line(10000, null, 'x'.repeat(45)), // 45 chars / 15 per s = 3 s
      line(20000, null, 'x'.repeat(300)), // 20 s capped at 7 s
      line(30000, null, 'x'.repeat(60)), // 4 s, but the next line starts after 1 s
      line(31000, 40000, 'chat end kept'),
      line(50000, 90000, 'chat end past the chunk end'),
    ],
    60000,
  );
  assert.deepEqual(ends.map((cue) => cue.endMs), [1500, 13000, 27000, 31000, 40000, 60000]);
  assert.deepEqual(ends.map((cue) => cue.startMs), [0, 10000, 20000, 30000, 31000, 50000]);
});

test('reading-time end: lines starting at or after the chunk end are dropped', () => {
  assert.deepEqual(withReadingTimeEnds([line(1000, null, 'a'), line(5000, null, 'b')], 5000), [line(1000, 2500, 'a')]);
});

test('formatPromptTime: 65000 → "1:05"; 3725000 → "1:02:05"', () => {
  assert.equal(formatPromptTime(65000), '1:05');
  assert.equal(formatPromptTime(3725000), '1:02:05');
  assert.equal(formatPromptTime(0), '0:00');
  assert.equal(formatPromptTime(65400), '1:05');
  assert.equal(formatPromptTime(65400, { roundUp: true }), '1:06');
});
