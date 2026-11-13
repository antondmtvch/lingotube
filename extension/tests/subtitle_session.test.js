import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SubtitleSession } from '../src/page/subtitle_session.js';
import { CaptionsUnavailableError } from '../src/page/youtube_captions_source.js';
import { ChatRateLimitedError } from '../src/shared/chat_errors.js';
import { STATUS_TEXTS, rateLimitedText } from '../src/shared/status_texts.js';

const VIDEO_ID = 'Vid-3xample';
const RUSSIAN = { code: 'ru', name: 'Russian' };
const NOW_MS = 1_000_000;

/** Cues one second apart, each 900 ms long. */
function cuesOf(count) {
  return Array.from({ length: count }, (_, id) => ({
    id,
    startMs: id * 1000,
    endMs: id * 1000 + 900,
    sourceText: `source ${id}`,
  }));
}

function translationsOf(ids) {
  return Object.fromEntries(ids.map((id) => [String(id), `cached ${id}`]));
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

/** Fake translator: every call waits for the test to settle it. */
function controllableTranslator() {
  const calls = [];
  return {
    calls,
    translateCues: (cues) => new Promise((resolve, reject) => calls.push({ cues, resolve, reject })),
  };
}

function allTranslated(cues) {
  return { translationsByCueId: new Map(cues.map((cue) => [cue.id, `t${cue.id}`])), failedCueIds: [] };
}

function allFailed(cues) {
  return { translationsByCueId: new Map(), failedCueIds: cues.map((cue) => cue.id) };
}

/** Builds a session with recording fakes; `overrides` replace any constructor option. */
function sessionHarness({ cues = cuesOf(10), cachedEntry = null, overrides = {} } = {}) {
  const viewCalls = [];
  const overlayView = {};
  for (const method of ['showCueText', 'showStatus', 'clear', 'setHidden']) {
    overlayView[method] = (argument) => viewCalls.push(argument === undefined ? [method] : [method, argument]);
  }
  const cacheCalls = { loads: [], saves: [] };
  const cache = {
    load: async (key) => {
      cacheCalls.loads.push(key);
      return cachedEntry;
    },
    save: async (key, entry) => {
      cacheCalls.saves.push({ key, entry: structuredClone(entry) });
    },
  };
  const translator = controllableTranslator();
  const createTranslatorCalls = [];
  const timer = { callback: null, intervalMs: null, isCleared: false, setCount: 0 };
  const statuses = [];
  const infoLogs = [];
  const playback = { positionMs: 0, isPaused: false };
  const options = {
    videoId: VIDEO_ID,
    language: RUSSIAN,
    loadCues: async () => ({ cues, sourceKey: 'en.asr' }),
    createTranslator: async (languageName) => {
      createTranslatorCalls.push(languageName);
      return translator;
    },
    cache,
    overlayView,
    getPositionMs: () => playback.positionMs,
    isPaused: () => playback.isPaused,
    setTimer: (callback, intervalMs) => {
      timer.callback = callback;
      timer.intervalMs = intervalMs;
      timer.setCount += 1;
      return 'timer-handle';
    },
    clearTimer: (handle) => {
      assert.equal(handle, 'timer-handle');
      timer.isCleared = true;
    },
    onStatusChanged: (statusText, details) => statuses.push([statusText, details]),
    logInfo: (...parts) => infoLogs.push(parts),
    now: () => NOW_MS,
    ...overrides,
  };
  const session = new SubtitleSession(options);
  return {
    session,
    viewCalls,
    cacheCalls,
    translator,
    createTranslatorCalls,
    timer,
    statuses,
    infoLogs,
    playback,
    /** Runs one timer tick the way the real interval would, then lets promises settle. */
    async tick() {
      if (timer.callback && !timer.isCleared) timer.callback();
      await flush();
    },
  };
}

test('shows "Перевожу…" then the translated cue text for the current position', async () => {
  const harness = sessionHarness();
  await harness.session.start();
  assert.equal(harness.timer.intervalMs, 250);
  harness.playback.positionMs = 500;
  await harness.tick();
  assert.deepEqual(harness.viewCalls.at(-1), ['showStatus', STATUS_TEXTS.translating]);
  assert.deepEqual(harness.createTranslatorCalls, ['Russian']);
  assert.equal(harness.translator.calls.length, 1);

  const { cues, resolve } = harness.translator.calls[0];
  resolve(allTranslated(cues));
  await flush();
  await harness.tick();
  assert.deepEqual(harness.viewCalls.at(-1), ['showCueText', 't0']);

  // The cache entry has exactly the {translations: {<cueId>: string}} shape.
  assert.equal(harness.cacheCalls.saves.length, 1);
  const { key, entry } = harness.cacheCalls.saves[0];
  assert.match(key, /^cache:Vid-3xample\|ru\|en\.asr\|/);
  assert.deepEqual(Object.keys(entry), ['translations']);
  assert.deepEqual(entry.translations, Object.fromEntries(cues.map((cue) => [String(cue.id), `t${cue.id}`])));
});

test('cached translations are shown without creating a translator', async () => {
  const harness = sessionHarness({ cachedEntry: { translations: translationsOf([...Array(10).keys()]) } });
  await harness.session.start();
  harness.playback.positionMs = 2100;
  await harness.tick();
  await harness.tick();
  assert.deepEqual(harness.viewCalls.at(-1), ['showCueText', 'cached 2']);
  assert.deepEqual(harness.createTranslatorCalls, []);
  assert.equal(harness.cacheCalls.saves.length, 0);
});

test('a gap between cues clears the box', async () => {
  const harness = sessionHarness({ cachedEntry: { translations: translationsOf([...Array(10).keys()]) } });
  await harness.session.start();
  harness.playback.positionMs = 2100;
  await harness.tick();
  harness.playback.positionMs = 2950;
  await harness.tick();
  assert.deepEqual(harness.viewCalls.at(-1), ['clear']);
});

test('after stop() a late translator reply never reaches the view or the cache', async () => {
  const harness = sessionHarness();
  await harness.session.start();
  await harness.tick();
  assert.equal(harness.translator.calls.length, 1);
  const viewCallCountAtStop = harness.viewCalls.length;
  const statusCountAtStop = harness.statuses.length;

  harness.session.stop();
  harness.session.stop();
  assert.equal(harness.timer.isCleared, true);
  const { cues, resolve } = harness.translator.calls[0];
  resolve(allTranslated(cues));
  await flush();
  // Even a stray timer callback after stop() must not render anything.
  harness.timer.callback();
  await flush();

  assert.equal(harness.viewCalls.length, viewCallCountAtStop);
  assert.equal(harness.statuses.length, statusCountAtStop);
  assert.equal(harness.cacheCalls.saves.length, 0);
});

test('stop() during loadCues: the session does not start its timer', async () => {
  let finishLoading;
  const harness = sessionHarness({
    overrides: {
      loadCues: () => new Promise((resolve) => {
        finishLoading = resolve;
      }),
    },
  });
  const starting = harness.session.start();
  harness.session.stop();
  finishLoading({ cues: cuesOf(3), sourceKey: 'en.asr' });
  await starting;
  assert.equal(harness.timer.setCount, 0);
  assert.deepEqual(harness.cacheCalls.loads, []);
  assert.deepEqual(harness.statuses, []);
  assert.deepEqual(harness.infoLogs, []);
});

test('stop() during the cache load: the session does not start its timer', async () => {
  let finishCacheLoad;
  const slowCache = {
    load: () => new Promise((resolve) => {
      finishCacheLoad = resolve;
    }),
    save: async () => {},
  };
  const slowHarness = sessionHarness({ overrides: { cache: slowCache } });
  const starting = slowHarness.session.start();
  await flush();
  slowHarness.session.stop();
  finishCacheLoad(null);
  await starting;
  assert.equal(slowHarness.timer.setCount, 0);
});

test('captions that cannot be fetched report the status, show nothing and start no timer', async () => {
  for (const loadCues of [
    async () => {
      throw new CaptionsUnavailableError('no track');
    },
    async () => ({ cues: [], sourceKey: 'en.asr' }),
  ]) {
    const harness = sessionHarness({ overrides: { loadCues } });
    await harness.session.start();
    assert.deepEqual(harness.statuses.at(-1), [STATUS_TEXTS.captionsNotFetched, { canRetry: false }]);
    assert.equal(harness.timer.setCount, 0);
    assert.ok(harness.viewCalls.every(([method]) => method !== 'showCueText'));
    assert.deepEqual(harness.viewCalls.at(-1), ['clear']);
  }
});

test('a rate-limited stop reports the minutes text with canRetry true', async () => {
  const harness = sessionHarness();
  await harness.session.start();
  await harness.tick();
  harness.translator.calls[0].reject(new ChatRateLimitedError(NOW_MS + 90_001));
  await flush();
  assert.deepEqual(harness.statuses.at(-1), [rateLimitedText(2), { canRetry: true }]);
  await harness.tick();
  // The current cue has no translation: the box tells why instead of "Перевожу…".
  assert.deepEqual(harness.viewCalls.at(-1), ['showStatus', rateLimitedText(2)]);
  assert.equal(harness.translator.calls.length, 1);
});

test('a rate limit shorter than a minute still says one minute', async () => {
  const harness = sessionHarness();
  await harness.session.start();
  await harness.tick();
  harness.translator.calls[0].reject(new ChatRateLimitedError(NOW_MS + 5_000));
  await flush();
  assert.deepEqual(harness.statuses.at(-1), [rateLimitedText(1), { canRetry: true }]);
});

test('the session resumes by itself when the rate limit has passed', async () => {
  let nowMs = NOW_MS;
  const harness = sessionHarness({ overrides: { now: () => nowMs } });
  await harness.session.start();
  await harness.tick();
  harness.translator.calls[0].reject(new ChatRateLimitedError(NOW_MS + 60_000));
  await flush();
  await harness.tick();
  assert.equal(harness.translator.calls.length, 1);
  nowMs = NOW_MS + 60_000;
  await harness.tick();
  assert.deepEqual(harness.statuses.at(-1), [null, { canRetry: false }]);
  await harness.tick();
  assert.equal(harness.translator.calls.length, 2);
});

test('retry after a stop resumes ticking and re-schedules failed cues', async () => {
  const harness = sessionHarness({
    cues: cuesOf(100),
    overrides: { schedule: { reserveAheadMs: 120000, batchSize: 2 } },
  });
  await harness.session.start();
  for (let message = 0; message < 3; message += 1) {
    await harness.tick();
    const call = harness.translator.calls[message];
    call.resolve(allFailed(call.cues));
    await flush();
  }
  assert.deepEqual(harness.statuses.at(-1), [STATUS_TEXTS.repeatedFailures, { canRetry: false }]);
  await harness.tick();
  assert.equal(harness.translator.calls.length, 3);

  harness.session.retry();
  assert.deepEqual(harness.statuses.at(-1), [null, { canRetry: false }]);
  await harness.tick();
  assert.equal(harness.translator.calls.length, 4);
  assert.deepEqual(harness.translator.calls[3].cues.map((cue) => cue.id), [0, 1]);
});

test('other pump stop reasons map to their status texts', async () => {
  const { ChatUnavailableError, NotSignedInError } = await import('../src/shared/chat_errors.js');
  for (const [error, statusText] of [
    [new ChatUnavailableError(), STATUS_TEXTS.chatUnavailable],
    [new NotSignedInError(), STATUS_TEXTS.notSignedIn],
  ]) {
    const harness = sessionHarness();
    await harness.session.start();
    await harness.tick();
    harness.translator.calls[0].reject(error);
    await flush();
    assert.deepEqual(harness.statuses.at(-1), [statusText, { canRetry: false }]);
  }
});

test('a translator that cannot be created is retried on the next batch', async () => {
  let attempts = 0;
  const translator = controllableTranslator();
  const harness = sessionHarness({
    overrides: {
      createTranslator: async () => {
        attempts += 1;
        if (attempts === 1) throw new Error('chat request failed');
        return translator;
      },
    },
  });
  await harness.session.start();
  await harness.tick();
  await harness.tick();
  assert.equal(attempts, 2);
  assert.equal(translator.calls.length, 1);
});

test('a cache that fails to load or save does not stop subtitles', async () => {
  const brokenCache = {
    load: async () => {
      throw new Error('storage timeout');
    },
    save: () => {
      throw new Error('quota exceeded');
    },
  };
  const harness = sessionHarness({ overrides: { cache: brokenCache } });
  await harness.session.start();
  await harness.tick();
  const { cues, resolve } = harness.translator.calls[0];
  resolve(allTranslated(cues));
  await flush();
  await harness.tick();
  assert.deepEqual(harness.viewCalls.at(-1), ['showCueText', 't0']);

  const rejectingSaveHarness = sessionHarness({
    overrides: { cache: { load: async () => null, save: async () => Promise.reject(new Error('quota')) } },
  });
  await rejectingSaveHarness.session.start();
  await rejectingSaveHarness.tick();
  const call = rejectingSaveHarness.translator.calls[0];
  call.resolve(allTranslated(call.cues));
  await flush();
  await rejectingSaveHarness.tick();
  assert.deepEqual(rejectingSaveHarness.viewCalls.at(-1), ['showCueText', 't0']);
});

test('while paused, no translation is requested once the reserve is satisfied', async () => {
  // Cues 0..199 s; the first 150 s are cached, so at 0 s the 120 s reserve is satisfied.
  const harness = sessionHarness({
    cues: cuesOf(200),
    cachedEntry: { translations: translationsOf([...Array(150).keys()]) },
  });
  await harness.session.start();
  harness.playback.isPaused = true;
  for (let tick = 0; tick < 5; tick += 1) await harness.tick();
  assert.deepEqual(harness.createTranslatorCalls, []);
  assert.deepEqual(harness.viewCalls.at(-1), ['showCueText', 'cached 0']);
});

test('while paused with a short reserve, the reserve is topped up and then requests stop', async () => {
  const harness = sessionHarness({
    cues: cuesOf(200),
    cachedEntry: { translations: translationsOf([...Array(150).keys()]) },
    overrides: { schedule: { reserveAheadMs: 120000, batchSize: 50 } },
  });
  await harness.session.start();
  harness.playback.isPaused = true;
  harness.playback.positionMs = 40_000; // 110 s translated ahead: short of 120 s
  await harness.tick();
  assert.equal(harness.translator.calls.length, 1);
  const { cues, resolve } = harness.translator.calls[0];
  resolve(allTranslated(cues));
  await flush();
  for (let tick = 0; tick < 5; tick += 1) await harness.tick();
  assert.equal(harness.translator.calls.length, 1);
});

test('an ad clears and hides the box, stops ticks, and the end of the ad shows no stale text', async () => {
  const harness = sessionHarness({ cachedEntry: { translations: translationsOf([...Array(10).keys()]) } });
  await harness.session.start();
  harness.playback.positionMs = 1500;
  await harness.tick();
  assert.deepEqual(harness.viewCalls.at(-1), ['showCueText', 'cached 1']);

  harness.session.setAdPlaying(true);
  assert.deepEqual(harness.viewCalls.slice(-2), [['clear'], ['setHidden', true]]);
  const viewCallCountDuringAd = harness.viewCalls.length;
  harness.playback.positionMs = 5500; // the ad's own video position
  await harness.tick();
  assert.equal(harness.viewCalls.length, viewCallCountDuringAd);

  harness.session.setAdPlaying(false);
  assert.deepEqual(harness.viewCalls.at(-1), ['setHidden', false]);
  harness.playback.positionMs = 1500;
  await harness.tick();
  assert.deepEqual(harness.viewCalls.at(-1), ['showCueText', 'cached 1']);
});

test('an ad that starts before the cues are loaded gets no "Перевожу…" text', async () => {
  let finishLoading;
  const harness = sessionHarness({
    overrides: {
      loadCues: () => new Promise((resolve) => {
        finishLoading = resolve;
      }),
    },
  });
  harness.session.setAdPlaying(true);
  const starting = harness.session.start();
  assert.ok(harness.viewCalls.every(([method]) => method !== 'showStatus'));
  finishLoading({ cues: cuesOf(3), sourceKey: 'en.asr' });
  await starting;
  await harness.tick();
  assert.equal(harness.translator.calls.length, 0);
});

test('the session logs one start line with counts and never the video id', async () => {
  const harness = sessionHarness({ cachedEntry: { translations: translationsOf([0, 1]) } });
  await harness.session.start();
  await harness.tick();
  harness.session.stop();
  assert.equal(harness.infoLogs.length, 1);
  assert.equal(harness.infoLogs[0][0], 'lingotube: session started');
  const logged = JSON.stringify(harness.infoLogs);
  assert.ok(!logged.includes(VIDEO_ID), logged);
  assert.deepEqual(harness.infoLogs[0][1], { cues: 10, cachedTranslations: 2 });
});
