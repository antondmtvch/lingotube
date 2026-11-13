import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CueTrack } from '../src/shared/cue_track.js';
import { DEFAULT_SCHEDULE, chooseNextBatch } from '../src/shared/translation_schedule.js';

/** Cues of one second each, one per second, ids equal to the second. */
function trackOfCues(count) {
  const cues = [];
  for (let id = 0; id < count; id += 1) {
    cues.push({ id, startMs: id * 1000, endMs: id * 1000 + 900, sourceText: `source ${id}` });
  }
  return new CueTrack(cues);
}

test('the default schedule keeps 120000 ms ahead in batches of 30', () => {
  assert.deepEqual(DEFAULT_SCHEDULE, { reserveAheadMs: 120000, batchSize: 30 });
});

test('nothing is scheduled while 120000 ms ahead are translated', () => {
  const track = trackOfCues(400);
  for (let id = 0; id <= 120; id += 1) track.setTranslation(id, `t${id}`);
  // First untranslated cue (121) starts exactly 120000 ms after position 1000.
  assert.deepEqual(chooseNextBatch(track, 1000), []);
  assert.equal(chooseNextBatch(track, 2000).length, 30); // 119000 ms ahead: not enough
});

test('the first batch starts at the cue under the playhead, not at the beginning', () => {
  const track = trackOfCues(1000);
  const batch = chooseNextBatch(track, 600000);
  assert.equal(batch[0].id, 600);
});

test('a batch has at most 30 cues', () => {
  assert.equal(chooseNextBatch(trackOfCues(100), 0).length, 30);
  assert.equal(chooseNextBatch(trackOfCues(10), 0).length, 10);
});

test('a custom schedule changes the batch size', () => {
  assert.equal(chooseNextBatch(trackOfCues(100), 0, { reserveAheadMs: 120000, batchSize: 5 }).length, 5);
});

test('after a seek into untranslated video the batch starts at the new position', () => {
  const track = trackOfCues(1000);
  for (let id = 0; id < 200; id += 1) track.setTranslation(id, `t${id}`);
  assert.equal(chooseNextBatch(track, 500000)[0].id, 500);
});

test('failed cues are not scheduled again', () => {
  const track = trackOfCues(100);
  track.markFailed([0, 1, 2]);
  assert.equal(chooseNextBatch(track, 0)[0].id, 3);
});
