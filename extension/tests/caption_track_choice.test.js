import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chooseCaptionTrack } from '../src/shared/caption_track_choice.js';

const track = (languageCode, kind) => ({ languageCode, kind, baseUrl: `/${languageCode}-${kind}` });

test('no tracks gives null', () => {
  assert.equal(chooseCaptionTrack([]), null);
});

test('a manual track in the original language wins over the asr track', () => {
  const manualEn = track('en', 'manual');
  assert.equal(chooseCaptionTrack([track('en', 'asr'), manualEn]), manualEn);
});

test('without a manual track in that language the asr track is chosen', () => {
  const asrEn = track('en', 'asr');
  assert.equal(chooseCaptionTrack([track('ru', 'manual'), asrEn]), asrEn);
});

test('without asr tracks the first manual track is chosen', () => {
  const first = track('de', 'manual');
  assert.equal(chooseCaptionTrack([first, track('fr', 'manual')]), first);
});

test('tracks of other languages never win over the original language', () => {
  const asrEn = track('en', 'asr');
  assert.equal(chooseCaptionTrack([asrEn, track('ru', 'asr'), track('ru', 'manual')]), asrEn);
});
