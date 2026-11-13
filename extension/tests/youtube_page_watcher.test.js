import { test } from 'node:test';
import assert from 'node:assert/strict';
import { watchYouTubePage } from '../src/page/youtube_page_watcher.js';

/** A fake page: a document with event listeners and an optional #movie_player, a window with a URL. */
function fakePage(initialUrl) {
  const listeners = new Map();
  const observers = [];
  const playerClasses = new Set();
  const playerElement = { classList: { contains: (name) => playerClasses.has(name) } };
  const page = {
    playerElement: null,
    observers,
    document: {
      addEventListener(type, listener) {
        listeners.set(type, listener);
      },
      removeEventListener(type, listener) {
        if (listeners.get(type) === listener) listeners.delete(type);
      },
      querySelector: (selector) => (selector === '#movie_player' ? page.playerElement : null),
    },
    window: {
      location: { href: initialUrl },
      MutationObserver: class {
        constructor(callback) {
          this.callback = callback;
          this.target = null;
          observers.push(this);
        }
        observe(target) {
          this.target = target;
        }
        disconnect() {
          this.target = null;
        }
      },
    },
    navigate(url) {
      page.window.location.href = url;
      listeners.get('yt-navigate-finish')?.({});
    },
    showPlayer() {
      page.playerElement = playerElement;
    },
    setAdShowing(isShowing) {
      if (isShowing) playerClasses.add('ad-showing');
      else playerClasses.delete('ad-showing');
      for (const observer of observers) if (observer.target) observer.callback([]);
    },
    hasNavigateListener: () => listeners.has('yt-navigate-finish'),
  };
  return page;
}

test('reports the initial video and each change of video, once per change', () => {
  const page = fakePage('https://www.youtube.com/watch?v=AAAAAAAAAAA');
  const videoIds = [];
  watchYouTubePage({
    document: page.document,
    window: page.window,
    onVideoChanged: (videoId) => videoIds.push(videoId),
    onAdStateChanged: () => {},
  });
  page.navigate('https://www.youtube.com/watch?v=AAAAAAAAAAA&t=30s');
  page.navigate('https://www.youtube.com/watch?v=BBBBBBBBBBB');
  page.navigate('https://www.youtube.com/@channel');
  page.navigate('https://www.youtube.com/watch?v=BBBBBBBBBBB');
  assert.deepEqual(videoIds, ['AAAAAAAAAAA', 'BBBBBBBBBBB', null, 'BBBBBBBBBBB']);
});

test('ad state follows the ad-showing class of the player, also when the player appears late', () => {
  const page = fakePage('https://www.youtube.com/');
  const adStates = [];
  watchYouTubePage({
    document: page.document,
    window: page.window,
    onVideoChanged: () => {},
    onAdStateChanged: (isAdPlaying) => adStates.push(isAdPlaying),
  });
  page.showPlayer();
  page.setAdShowing(true);
  page.navigate('https://www.youtube.com/watch?v=AAAAAAAAAAA');
  page.setAdShowing(true);
  page.setAdShowing(false);
  page.setAdShowing(false);
  assert.deepEqual(adStates, [true, false]);
});

test('stop() removes the navigation listener and disconnects the observer', () => {
  const page = fakePage('https://www.youtube.com/watch?v=AAAAAAAAAAA');
  page.showPlayer();
  const videoIds = [];
  const watcher = watchYouTubePage({
    document: page.document,
    window: page.window,
    onVideoChanged: (videoId) => videoIds.push(videoId),
    onAdStateChanged: () => {},
  });
  watcher.stop();
  watcher.stop();
  assert.equal(page.hasNavigateListener(), false);
  assert.ok(page.observers.every((observer) => observer.target === null));
  page.navigate('https://www.youtube.com/watch?v=BBBBBBBBBBB');
  assert.deepEqual(videoIds, ['AAAAAAAAAAA']);
});
