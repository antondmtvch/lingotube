import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  mergePlayerRequestParameters,
  isPlayerCaptionRequest,
  capturePlayerCaptionRequestUrl,
} from '../src/page/player_caption_request.js';

test('merge adds pot and client parameters, keeps the track own lang/kind, drops tlang, sets fmt=json3', () => {
  const merged = new URL(
    mergePlayerRequestParameters(
      'https://www.youtube.com/api/timedtext?v=abc&lang=en&kind=asr&sig=S',
      'https://www.youtube.com/api/timedtext?v=abc&lang=ru&tlang=de&pot=P&c=WEB&cver=2.1&sig=OTHER&fmt=srv3',
    ),
  );
  assert.equal(merged.searchParams.get('pot'), 'P');
  assert.equal(merged.searchParams.get('c'), 'WEB');
  assert.equal(merged.searchParams.get('cver'), '2.1');
  assert.equal(merged.searchParams.get('lang'), 'en');
  assert.equal(merged.searchParams.get('kind'), 'asr');
  assert.equal(merged.searchParams.get('sig'), 'S');
  assert.equal(merged.searchParams.has('tlang'), false);
  assert.equal(merged.searchParams.get('fmt'), 'json3');
  assert.equal(merged.origin, 'https://www.youtube.com');
});

test('a request without pot is not a player caption request', () => {
  assert.equal(isPlayerCaptionRequest('https://www.youtube.com/api/timedtext?v=a&fmt=json3'), false);
  assert.equal(isPlayerCaptionRequest('https://www.youtube.com/api/timedtext?v=a&pot=P'), true);
  assert.equal(isPlayerCaptionRequest('https://www.youtube.com/other?pot=P'), false);
  assert.equal(isPlayerCaptionRequest('not a url'), false);
});

function createFakeEnvironment({ alreadySeen = [], subtitlesOn = false, requestOnClick = true }) {
  const clicks = [];
  const classes = new Set();
  let callback = null;
  const emit = (name) => callback?.({ getEntries: () => [{ name }] });
  const button = {
    state: subtitlesOn,
    getAttribute: () => String(button.state),
    click() {
      button.state = !button.state;
      clicks.push(button.state);
      if (button.state && requestOnClick) {
        emit('https://www.youtube.com/api/timedtext?v=a&pot=NEW');
      }
    },
  };
  const player = { classList: { add: (name) => classes.add(name), remove: (name) => classes.delete(name) } };
  const document = {
    querySelector: (selector) =>
      selector === '#movie_player' ? player : selector === '.ytp-subtitles-button' ? button : null,
  };
  class FakePerformanceObserver {
    constructor(observerCallback) {
      callback = observerCallback;
    }
    observe() {
      queueMicrotask(() => alreadySeen.forEach(emit));
    }
    disconnect() {}
  }
  const sleep = async () => {
    await new Promise((resolve) => setImmediate(resolve));
  };
  return { document, button, classes, clicks, performanceObserverClass: FakePerformanceObserver, sleep };
}

test('capture returns an earlier player request without touching the button', async () => {
  const env = createFakeEnvironment({ alreadySeen: ['https://www.youtube.com/api/timedtext?v=a&pot=OLD'] });
  const url = await capturePlayerCaptionRequestUrl(env);
  assert.match(url, /pot=OLD/);
  assert.deepEqual(env.clicks, []);
});

test('capture ignores requests without pot and forces one with the button, then restores it', async () => {
  const env = createFakeEnvironment({ alreadySeen: ['https://www.youtube.com/api/timedtext?v=a&fmt=json3'] });
  const url = await capturePlayerCaptionRequestUrl(env);
  assert.match(url, /pot=NEW/);
  assert.equal(env.button.state, false);
  assert.equal(env.classes.size, 0);
});

test('capture turns subtitles off and on again when they were on, ending on', async () => {
  const env = createFakeEnvironment({ subtitlesOn: true });
  const url = await capturePlayerCaptionRequestUrl(env);
  assert.match(url, /pot=NEW/);
  assert.deepEqual(env.clicks, [false, true]);
  assert.equal(env.button.state, true);
});

test('capture returns null and restores the button when no request comes', async () => {
  const env = createFakeEnvironment({ requestOnClick: false });
  assert.equal(await capturePlayerCaptionRequestUrl({ ...env, timeoutMs: 300 }), null);
  assert.equal(env.button.state, false);
  assert.equal(env.classes.size, 0);
});
