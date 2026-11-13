import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  mergePlayerRequestParameters,
  isPlayerCaptionRequest,
  capturePlayerCaptionRequestUrl,
  createSerialCaptionCapture,
  activateSubtitleButton,
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

test('merge does not copy the player lang/kind/name into a manual track URL', () => {
  const merged = new URL(
    mergePlayerRequestParameters(
      'https://www.youtube.com/api/timedtext?v=abc&lang=de',
      'https://www.youtube.com/api/timedtext?v=abc&lang=en&kind=asr&name=Auto&pot=P&c=WEB',
    ),
  );
  assert.equal(merged.searchParams.has('kind'), false);
  assert.equal(merged.searchParams.has('name'), false);
  assert.equal(merged.searchParams.get('lang'), 'de');
  assert.equal(merged.searchParams.get('pot'), 'P');
});

test('a request without pot is not a player caption request', () => {
  assert.equal(isPlayerCaptionRequest('https://www.youtube.com/api/timedtext?v=a&fmt=json3'), false);
  assert.equal(isPlayerCaptionRequest('https://www.youtube.com/api/timedtext?v=a&pot=P'), true);
  assert.equal(isPlayerCaptionRequest('https://www.youtube.com/other?pot=P'), false);
  assert.equal(isPlayerCaptionRequest('not a url'), false);
});

// Node has no DOM events: a plain record of type and options stands in for them.
globalThis.MouseEvent ??= class {
  constructor(type, init = {}) {
    this.type = type;
    Object.assign(this, init);
  }
};

// A button like the live player's: `.click()` does nothing, only dispatched events toggle it.
function createEventOnlyButton({ toggleOn, subtitlesOn = false }) {
  const receivedTypes = [];
  const button = {
    state: subtitlesOn,
    receivedTypes,
    methodClicks: 0,
    getAttribute: () => String(button.state),
    dispatchEvent(event) {
      receivedTypes.push(event.type);
      if (event.type === toggleOn) button.state = !button.state;
      return true;
    },
    click() {
      button.methodClicks += 1;
    },
  };
  return button;
}

function createFakeEnvironment({ alreadySeen = [], subtitlesOn = false, requestOnClick = true }) {
  const clicks = [];
  const classes = new Set();
  let callback = null;
  const emit = (name) => callback?.({ getEntries: () => [{ name }] });
  const button = {
    state: subtitlesOn,
    getAttribute: () => String(button.state),
    dispatchEvent(event) {
      if (event.type === 'click') button.click();
      return true;
    },
    click() {
      button.state = !button.state;
      clicks.push(button.state);
      if (button.state && requestOnClick) {
        emit('https://www.youtube.com/api/timedtext?v=a&pot=NEW');
      }
    },
  };
  const player = {
    classList: { add: (name) => classes.add(name), remove: (name) => classes.delete(name) },
    querySelector: (selector) => (selector === '.ytp-subtitles-button' ? button : null),
  };
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
  return { document, playerElement: player, button, classes, clicks, expectedVideoId: 'a', performanceObserverClass: FakePerformanceObserver, sleep };
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
});

test('capture does not change the native captions class, on success or on timeout', async () => {
  const succeeded = createFakeEnvironment({});
  await capturePlayerCaptionRequestUrl(succeeded);
  assert.equal(succeeded.classes.size, 0);

  const timedOut = createFakeEnvironment({ requestOnClick: false });
  await capturePlayerCaptionRequestUrl({ ...timedOut, timeoutMs: 300 });
  assert.equal(timedOut.classes.size, 0);

  const alreadyHidden = createFakeEnvironment({});
  alreadyHidden.classes.add('lingotube-hide-native-captions');
  await capturePlayerCaptionRequestUrl(alreadyHidden);
  assert.deepEqual([...alreadyHidden.classes], ['lingotube-hide-native-captions']);
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
});

test('capture ignores a buffered pot entry of another video and uses the button', async () => {
  const env = createFakeEnvironment({ alreadySeen: ['https://www.youtube.com/api/timedtext?v=other&pot=OLD'] });
  const url = await capturePlayerCaptionRequestUrl(env);
  assert.match(url, /pot=NEW/);
  assert.deepEqual(env.clicks, [true, false]);
});

test('capture takes a buffered pot entry of the expected video', async () => {
  const env = createFakeEnvironment({ alreadySeen: ['https://www.youtube.com/api/timedtext?v=a&pot=MATCH'] });
  assert.match(await capturePlayerCaptionRequestUrl(env), /pot=MATCH/);
  assert.deepEqual(env.clicks, []);
});

test('capture clicks the button inside the player, not the first one in the document', async () => {
  const env = createFakeEnvironment({});
  const wrongButton = { clicks: 0, getAttribute: () => 'false', click() { this.clicks += 1; } };
  const url = await capturePlayerCaptionRequestUrl({
    ...env,
    document: { querySelector: () => wrongButton, querySelectorAll: () => [wrongButton, env.button] },
  });
  assert.match(url, /pot=NEW/);
  assert.equal(wrongButton.clicks, 0);
  assert.deepEqual(env.clicks, [true, false]);
});

test('capture turns on an event-only button with the full pointer sequence before waiting for the request', async () => {
  const env = createFakeEnvironment({});
  const eventOnlyButton = createEventOnlyButton({ toggleOn: 'click' });
  const player = { ...env.playerElement, querySelector: () => eventOnlyButton };
  const pressedDuringSleeps = [];
  await capturePlayerCaptionRequestUrl({
    ...env,
    playerElement: player,
    timeoutMs: 200,
    sleep: async (ms) => {
      pressedDuringSleeps.push(eventOnlyButton.getAttribute('aria-pressed'));
      await env.sleep(ms);
    },
  });
  assert.deepEqual(eventOnlyButton.receivedTypes.slice(0, 4), ['pointerdown', 'mousedown', 'mouseup', 'click']);
  // The settle pause and the polls for the request all happen while the button is pressed.
  assert.ok(pressedDuringSleeps.filter((pressed) => pressed === 'true').length >= 3, String(pressedDuringSleeps));
  assert.equal(eventOnlyButton.state, false);
  assert.equal(eventOnlyButton.methodClicks, 0);
});

test('the sequence, not only click, is dispatched: a mousedown-only button turns on', async () => {
  const eventOnlyButton = createEventOnlyButton({ toggleOn: 'mousedown' });
  const result = await activateSubtitleButton(eventOnlyButton, async () => {});
  assert.equal(eventOnlyButton.state, true);
  assert.equal(result.pressedAfterActivation, true);
  assert.equal(result.fallbackUsed, false);
  assert.equal(eventOnlyButton.methodClicks, 0);
});

test('serial captures: the second starts only after the first has restored the button', async () => {
  const env = createFakeEnvironment({ subtitlesOn: true, requestOnClick: false });
  const steps = [];
  const captureSerially = createSerialCaptionCapture(async (options) => {
    steps.push(`start ${options.expectedVideoId} pressed=${env.button.state}`);
    try {
      return await capturePlayerCaptionRequestUrl(options);
    } finally {
      steps.push(`end ${options.expectedVideoId} pressed=${env.button.state} hidden=${env.classes.size > 0}`);
    }
  });
  const results = await Promise.all([
    captureSerially({ ...env, expectedVideoId: 'old', timeoutMs: 200 }),
    captureSerially({ ...env, expectedVideoId: 'new', timeoutMs: 200 }),
  ]);
  assert.deepEqual(results, [null, null]);
  assert.deepEqual(steps, [
    'start old pressed=true',
    'end old pressed=true hidden=false',
    'start new pressed=true',
    'end new pressed=true hidden=false',
  ]);
  assert.equal(env.button.state, true);
});

test('serial captures: a failed capture does not block the next one', async () => {
  let calls = 0;
  const captureSerially = createSerialCaptionCapture(async () => {
    calls += 1;
    if (calls === 1) throw new Error('capture failed');
    return 'url';
  });
  const first = captureSerially({});
  const second = captureSerially({});
  await assert.rejects(first);
  assert.equal(await second, 'url');
});
