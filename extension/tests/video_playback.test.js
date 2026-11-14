import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createVideoPlayback } from '../src/shared/video_playback.js';

function makeVideo({ paused = true, ended = false, playResult = Promise.resolve() } = {}) {
  const video = { paused, ended, playCalls: 0, pauseCalls: 0 };
  video.play = () => { video.playCalls += 1; return playResult; };
  video.pause = () => { video.pauseCalls += 1; };
  return video;
}

function makePlayback({ video, shownVideoId = 'a', sessionVideoId = 'a' }) {
  return createVideoPlayback({
    findVideoElement: () => video,
    readShownVideoId: () => shownVideoId,
    sessionVideoId,
  });
}

test('play resumes a paused video of the session video', () => {
  const video = makeVideo();
  makePlayback({ video }).play();
  assert.equal(video.playCalls, 1);
});

test('play does nothing for a playing video', () => {
  const video = makeVideo({ paused: false });
  makePlayback({ video }).play();
  assert.equal(video.playCalls, 0);
});

test('play does not restart an ended video', () => {
  const video = makeVideo({ ended: true });
  makePlayback({ video }).play();
  assert.equal(video.playCalls, 0);
});

test('play does nothing when the page shows another video than the session', () => {
  const video = makeVideo();
  makePlayback({ video, shownVideoId: 'b' }).play();
  assert.equal(video.playCalls, 0);
});

test('play does nothing without a video element', () => {
  const playback = makePlayback({ video: null });
  assert.doesNotThrow(() => playback.play());
});

test('a rejected play promise is swallowed', async () => {
  const video = makeVideo({ playResult: Promise.reject(new Error('NotAllowedError')) });
  makePlayback({ video }).play();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(video.playCalls, 1);
});

test('play tolerates a play() that returns no promise', () => {
  const video = makeVideo({ playResult: undefined });
  assert.doesNotThrow(() => makePlayback({ video }).play());
});

test('pause pauses the video of the session', () => {
  const video = makeVideo({ paused: false });
  makePlayback({ video }).pause();
  assert.equal(video.pauseCalls, 1);
});

test('pause does nothing for another video or without an element', () => {
  const video = makeVideo({ paused: false });
  makePlayback({ video, shownVideoId: 'b' }).pause();
  assert.equal(video.pauseCalls, 0);
  assert.doesNotThrow(() => makePlayback({ video: null }).pause());
});
