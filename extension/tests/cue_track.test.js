import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CueTrack } from '../src/shared/cue_track.js';

/** Three cues with a silence gap between the second and the third. */
function sampleCues() {
  return [
    { id: 1, startMs: 0, endMs: 1000, sourceText: 'one' },
    { id: 2, startMs: 1000, endMs: 2000, sourceText: 'two' },
    { id: 3, startMs: 3000, endMs: 4000, sourceText: 'three' },
  ];
}

test('cues are exposed in order', () => {
  const track = new CueTrack(sampleCues());
  assert.deepEqual(track.cues.map((cue) => cue.id), [1, 2, 3]);
});

test('cueAt hits the exact startMs and misses the exact endMs', () => {
  const track = new CueTrack(sampleCues());
  assert.equal(track.cueAt(0).id, 1);
  assert.equal(track.cueAt(999).id, 1);
  assert.equal(track.cueAt(1000).id, 2);
  assert.equal(track.cueAt(3000).id, 3);
  assert.equal(track.cueAt(4000), null);
});

test('cueAt returns null in a gap, before the first cue and in an empty track', () => {
  const track = new CueTrack(sampleCues());
  assert.equal(track.cueAt(2500), null);
  assert.equal(track.cueAt(-1), null);
  assert.equal(new CueTrack([]).cueAt(0), null);
});

test('cueAt works on a long track', () => {
  const cues = Array.from({ length: 2000 }, (_, index) => ({
    id: index + 1,
    startMs: index * 1000,
    endMs: index * 1000 + 800,
    sourceText: `cue ${index}`,
  }));
  const track = new CueTrack(cues);
  assert.equal(track.cueAt(1234500).id, 1235);
  assert.equal(track.cueAt(1234900), null);
});

test('translation state starts as none and follows the transitions', () => {
  const track = new CueTrack(sampleCues());
  assert.equal(track.translationState(1), 'none');
  track.markPending([1, 2]);
  assert.equal(track.translationState(1), 'pending');
  assert.equal(track.translationState(3), 'none');
  track.setTranslation(1, 'uno');
  assert.equal(track.translationState(1), 'done');
  track.markFailed([2]);
  assert.equal(track.translationState(2), 'failed');
});

test('resetPending turns pending into none and keeps the rest', () => {
  const track = new CueTrack(sampleCues());
  track.markPending([1, 2]);
  track.setTranslation(2, 'dos');
  track.markFailed([3]);
  track.resetPending();
  assert.equal(track.translationState(1), 'none');
  assert.equal(track.translationState(2), 'done');
  assert.equal(track.translationState(3), 'failed');
});

test('resetFailed turns failed into none and keeps the rest', () => {
  const track = new CueTrack(sampleCues());
  track.markFailed([1]);
  track.markPending([2]);
  track.resetFailed();
  assert.equal(track.translationState(1), 'none');
  assert.equal(track.translationState(2), 'pending');
});

test('loadTranslations marks known cues done and ignores unknown ids', () => {
  const track = new CueTrack(sampleCues());
  track.loadTranslations({ 1: 'uno', 99: 'ghost' });
  assert.equal(track.translationState(1), 'done');
  assert.equal(track.translationState(99), 'none');
  assert.deepEqual(track.translationsByCueId(), { 1: 'uno' });
});

test('translationsByCueId contains done cues only', () => {
  const track = new CueTrack(sampleCues());
  track.markPending([1]);
  track.markFailed([2]);
  track.setTranslation(3, 'tres');
  assert.deepEqual(track.translationsByCueId(), { 3: 'tres' });
});

test('displayAt maps cue state to what is shown', () => {
  const track = new CueTrack(sampleCues());
  assert.deepEqual(track.displayAt(2500), { kind: 'nothing' });
  assert.deepEqual(track.displayAt(500), { kind: 'waiting' });
  track.markPending([1]);
  assert.deepEqual(track.displayAt(500), { kind: 'waiting' });
  track.setTranslation(1, 'uno');
  assert.deepEqual(track.displayAt(500), { kind: 'text', text: 'uno' });
  track.markFailed([2]);
  assert.deepEqual(track.displayAt(1500), { kind: 'failed' });
});

test('translatedAheadMs is 0 when the current cue is untranslated', () => {
  const track = new CueTrack(sampleCues());
  assert.equal(track.translatedAheadMs(500), 0);
  track.markPending([1]);
  assert.equal(track.translatedAheadMs(500), 0);
});

test('translatedAheadMs runs to the first none or pending cue; failed counts as covered', () => {
  const track = new CueTrack(sampleCues());
  track.setTranslation(1, 'uno');
  track.markFailed([2]);
  assert.equal(track.translatedAheadMs(500), 2500);
  track.markPending([3]);
  assert.equal(track.translatedAheadMs(500), 2500);
});

test('translatedAheadMs is Infinity when nothing is left', () => {
  const track = new CueTrack(sampleCues());
  track.setTranslation(1, 'uno');
  track.setTranslation(2, 'dos');
  track.setTranslation(3, 'tres');
  assert.equal(track.translatedAheadMs(0), Infinity);
  assert.equal(track.translatedAheadMs(5000), Infinity);
});

test('untranslatedFrom starts at the containing or next cue, honours the limit', () => {
  const track = new CueTrack(sampleCues());
  assert.deepEqual(track.untranslatedFrom(1500, 10).map((cue) => cue.id), [2, 3]);
  assert.deepEqual(track.untranslatedFrom(2500, 10).map((cue) => cue.id), [3]);
  assert.deepEqual(track.untranslatedFrom(0, 2).map((cue) => cue.id), [1, 2]);
});

test('untranslatedFrom skips done, pending and failed cues', () => {
  const track = new CueTrack(sampleCues());
  track.setTranslation(1, 'uno');
  track.markPending([2]);
  track.markFailed([3]);
  assert.deepEqual(track.untranslatedFrom(0, 10), []);
});

test('two tracks do not share translation state', () => {
  const first = new CueTrack(sampleCues());
  const second = new CueTrack(sampleCues());
  first.setTranslation(1, 'uno');
  assert.equal(second.translationState(1), 'none');
});
