import assert from 'node:assert/strict';
import { test } from 'node:test';

import { WAIT_CAP_MS, decideWaitAction } from '../src/shared/subtitle_wait.js';

/** Waiting, playing video, nothing special: the base case each test tweaks. */
const BASE = {
  isEnabled: true,
  isWaiting: true,
  isAdPlaying: false,
  isPumpStopped: false,
  isAtVideoEnd: false,
  isVideoPaused: false,
  pausedByUs: false,
  waitStartedMs: 1000,
  isCapped: false,
  nowMs: 1000,
};

function decide(overrides) {
  return decideWaitAction({ ...BASE, ...overrides });
}

test('the wait cap is 30000 ms', () => {
  assert.equal(WAIT_CAP_MS, 30000);
});

test('pauses a playing video while the cue is waiting', () => {
  assert.deepEqual(decide({}), { action: 'pause', isCapped: false, pausedByUs: true });
});

test('a pause made by the user is never resumed by us', () => {
  const result = decide({
    isWaiting: false,
    isVideoPaused: true,
    pausedByUs: false,
    waitStartedMs: null,
    nowMs: 5000,
  });
  assert.equal(result.action, 'none');
  assert.equal(result.pausedByUs, false);
});

test('rule 1: our pause is dropped when the video is already playing again', () => {
  const result = decide({ pausedByUs: true, isVideoPaused: false });
  assert.deepEqual(result, { action: 'none', isCapped: false, pausedByUs: false });
});

test('rule 2: our pause is lifted when the wait is over', () => {
  const result = decide({ pausedByUs: true, isVideoPaused: true, isWaiting: false });
  assert.deepEqual(result, { action: 'play', isCapped: false, pausedByUs: false });
});

test('rule 2: an ad lifts our pause', () => {
  const result = decide({ pausedByUs: true, isVideoPaused: true, isAdPlaying: true });
  assert.deepEqual(result, { action: 'play', isCapped: false, pausedByUs: false });
});

test('rule 2: a disabled setting lifts our pause', () => {
  const result = decide({ pausedByUs: true, isVideoPaused: true, isEnabled: false });
  assert.deepEqual(result, { action: 'play', isCapped: false, pausedByUs: false });
});

test('rule 2: a stopped pump lifts our pause', () => {
  const result = decide({ pausedByUs: true, isVideoPaused: true, isPumpStopped: true });
  assert.deepEqual(result, { action: 'play', isCapped: false, pausedByUs: false });
});

test('rule 3: the end of the wait resets the cap', () => {
  const result = decide({ isWaiting: false, isCapped: true, waitStartedMs: null });
  assert.deepEqual(result, { action: 'none', isCapped: false, pausedByUs: false });
});

test('rule 4: after the cap no pause is set while the wait continues', () => {
  const result = decide({ isCapped: true, nowMs: 2000 });
  assert.deepEqual(result, { action: 'none', isCapped: true, pausedByUs: false });
});

test('rule 5: an ad prevents a new pause', () => {
  assert.equal(decide({ isAdPlaying: true }).action, 'none');
});

test('rule 5: a disabled setting prevents a new pause', () => {
  assert.equal(decide({ isEnabled: false }).action, 'none');
});

test('rule 5: a stopped pump prevents a new pause', () => {
  assert.equal(decide({ isPumpStopped: true }).action, 'none');
});

test('rule 5: the end of the video does not set a pause', () => {
  const result = decide({ isAtVideoEnd: true });
  assert.deepEqual(result, { action: 'none', isCapped: false, pausedByUs: false });
});

test('rule 6: after 30000 ms of waiting there is no pause and isCapped is true', () => {
  const result = decide({ waitStartedMs: 1000, nowMs: 1000 + WAIT_CAP_MS });
  assert.deepEqual(result, { action: 'none', isCapped: true, pausedByUs: false });
});

test('rule 7: just before the cap the video is still paused', () => {
  const result = decide({ waitStartedMs: 1000, nowMs: 1000 + WAIT_CAP_MS - 1 });
  assert.deepEqual(result, { action: 'pause', isCapped: false, pausedByUs: true });
});

test('rule 7: a wait with no start time pauses', () => {
  const result = decide({ waitStartedMs: null });
  assert.deepEqual(result, { action: 'pause', isCapped: false, pausedByUs: true });
});

test('rule 8: a video the user paused during the wait is left alone', () => {
  const result = decide({ isVideoPaused: true, pausedByUs: false });
  assert.deepEqual(result, { action: 'none', isCapped: false, pausedByUs: false });
});

test('our pause stays while the wait continues under the cap', () => {
  const result = decide({ isVideoPaused: true, pausedByUs: true, nowMs: 5000 });
  assert.deepEqual(result, { action: 'none', isCapped: false, pausedByUs: true });
});

test('our pause is lifted when the cap is reached', () => {
  const result = decide({
    isVideoPaused: true,
    pausedByUs: true,
    waitStartedMs: 1000,
    nowMs: 1000 + WAIT_CAP_MS,
  });
  assert.deepEqual(result, { action: 'play', isCapped: true, pausedByUs: false });
});

test('rule 2: the end of the video lifts our pause', () => {
  assert.deepEqual(
    decide({ pausedByUs: true, isVideoPaused: true, isAtVideoEnd: true }),
    { action: 'play', isCapped: false, pausedByUs: false },
  );
});

test('a wait dismissed by the user sets no pause while the wait continues', () => {
  assert.deepEqual(
    decide({ isDismissedByUser: true }),
    { action: 'none', isCapped: false, pausedByUs: false },
  );
});

test('a dismissed wait still reaches the cap and reports it', () => {
  assert.deepEqual(
    decide({ isDismissedByUser: true, nowMs: 1000 + WAIT_CAP_MS }),
    { action: 'none', isCapped: true, pausedByUs: false },
  );
});
