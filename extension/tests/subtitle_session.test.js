import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SubtitleSession } from '../src/page/subtitle_session.js';
import { CaptionsUnavailableError, NoCaptionTracksError } from '../src/page/youtube_captions_source.js';
import { ChatRateLimitedError } from '../src/shared/chat_errors.js';
import { STATUS_TEXTS, rateLimitedText } from '../src/shared/status_texts.js';
import { uiTexts } from '../src/shared/ui_strings.js';

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

/** Fake chat transcript source: every chunk request waits for the test to settle it. */
function controllableTranscriptSource() {
  const calls = [];
  return {
    calls,
    requestChunk: (index) => new Promise((resolve, reject) => calls.push({ index, resolve, reject })),
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
  for (const method of ['showCueText', 'showStatus', 'clear', 'setHidden', 'setApproximateTimingLabel']) {
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
  const transcriptSource = controllableTranscriptSource();
  const createTranscriptSourceCalls = [];
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
    createTranscriptSource: async (languageName, durationMs) => {
      createTranscriptSourceCalls.push([languageName, durationMs]);
      return transcriptSource;
    },
    getDurationMs: () => 900_000,
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
    transcriptSource,
    createTranscriptSourceCalls,
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

const noCaptionTracks = async () => {
  throw new NoCaptionTracksError('no track');
};

/** Lines of one chunk: two cues per chunk, 1 s and 10 s after its start. */
function chunkLines(index) {
  const startMs = index * 300_000;
  return [
    { startMs: startMs + 1000, endMs: startMs + 3000, text: `chunk ${index} a` },
    { startMs: startMs + 10_000, endMs: startMs + 12_000, text: `chunk ${index} b` },
  ];
}

test('no caption tracks → fallback mode with the approximate-timing label on', async () => {
  const harness = sessionHarness({ overrides: { loadCues: noCaptionTracks } });
  await harness.session.start();
  assert.ok(harness.viewCalls.some(([method, value]) => method === 'setApproximateTimingLabel' && value === true));
  assert.deepEqual(harness.statuses, []);
  harness.playback.positionMs = 2000;
  await harness.tick();
  assert.deepEqual(harness.viewCalls.at(-1), ['showStatus', STATUS_TEXTS.translating]);
  assert.deepEqual(harness.createTranscriptSourceCalls, [['Russian', 900_000]]);
  assert.deepEqual(harness.createTranslatorCalls, []);
  assert.deepEqual(harness.transcriptSource.calls.map((call) => call.index), [0]);

  harness.transcriptSource.calls[0].resolve(chunkLines(0));
  await flush();
  await harness.tick();
  assert.deepEqual(harness.viewCalls.at(-1), ['showCueText', 'chunk 0 a']);
  harness.playback.positionMs = 5000;
  await harness.tick();
  assert.deepEqual(harness.viewCalls.at(-1), ['clear']);

  // The chunk entry is saved under the chat transcript key, never under a caption key.
  assert.equal(harness.cacheCalls.saves.length, 1);
  const { key, entry } = harness.cacheCalls.saves[0];
  assert.match(key, /^cache:Vid-3xample\|ru\|chat\|/);
  assert.deepEqual(entry, { chunks: { 0: chunkLines(0) } });
  assert.deepEqual(harness.cacheCalls.loads, [key]);
});

test('captions exist but cannot be fetched → fallback plus the captionsNotFetched status', async () => {
  for (const loadCues of [
    async () => {
      throw new CaptionsUnavailableError('the player caption request was not captured');
    },
    async () => ({ cues: [], sourceKey: 'en.asr' }),
  ]) {
    const harness = sessionHarness({ overrides: { loadCues } });
    await harness.session.start();
    assert.deepEqual(harness.statuses, [[STATUS_TEXTS.captionsNotFetched, { canRetry: false }]]);
    assert.ok(harness.viewCalls.some(([method, value]) => method === 'setApproximateTimingLabel' && value === true));
    await harness.tick();
    assert.deepEqual(harness.viewCalls.at(-1), ['showStatus', STATUS_TEXTS.translating]);
    harness.transcriptSource.calls[0].resolve(chunkLines(0));
    await flush();
    harness.playback.positionMs = 1500;
    await harness.tick();
    // The first shown chunk takes over from the status line.
    assert.deepEqual(harness.viewCalls.at(-1), ['showCueText', 'chunk 0 a']);
    assert.deepEqual(harness.statuses.at(-1), [null, { canRetry: false }]);
    assert.equal(harness.statuses.length, 2);
  }
});

test('fallback: cached chunks are shown without opening the chat', async () => {
  const harness = sessionHarness({
    cachedEntry: { chunks: { 0: chunkLines(0) } },
    overrides: { loadCues: noCaptionTracks },
  });
  await harness.session.start();
  harness.playback.positionMs = 10_500;
  await harness.tick();
  await harness.tick();
  assert.deepEqual(harness.viewCalls.at(-1), ['showCueText', 'chunk 0 b']);
  assert.deepEqual(harness.createTranscriptSourceCalls, []);
});

test('fallback: the chunk under the playhead is requested first', async () => {
  const harness = sessionHarness({ overrides: { loadCues: noCaptionTracks } });
  harness.playback.positionMs = 620_000;
  await harness.session.start();
  await harness.tick();
  assert.deepEqual(harness.transcriptSource.calls.map((call) => call.index), [2]);
});

test('fallback: after stop() a late chunk reply never reaches the view or the cache', async () => {
  const harness = sessionHarness({ overrides: { loadCues: noCaptionTracks } });
  await harness.session.start();
  await harness.tick();
  const viewCallCountAtStop = harness.viewCalls.length;
  const statusCountAtStop = harness.statuses.length;
  harness.session.stop();
  harness.transcriptSource.calls[0].resolve(chunkLines(0));
  await flush();
  harness.timer.callback();
  await flush();
  assert.equal(harness.viewCalls.length, viewCallCountAtStop);
  assert.equal(harness.statuses.length, statusCountAtStop);
  assert.equal(harness.cacheCalls.saves.length, 0);
});

test('fallback: every chunk failing reports noSpeech without retry', async () => {
  const harness = sessionHarness({
    overrides: { loadCues: noCaptionTracks, getDurationMs: () => 200_000 },
  });
  await harness.session.start();
  await harness.tick();
  harness.transcriptSource.calls[0].resolve([]);
  await flush();
  assert.deepEqual(harness.statuses.at(-1), [STATUS_TEXTS.noSpeech, { canRetry: false }]);
  await harness.tick();
  assert.deepEqual(harness.viewCalls.at(-1), ['showStatus', STATUS_TEXTS.noSpeech]);
  assert.equal(harness.transcriptSource.calls.length, 1);
});

test('fallback: a rate limit stops with the minutes text and retry re-requests the chunk', async () => {
  const harness = sessionHarness({ overrides: { loadCues: noCaptionTracks } });
  await harness.session.start();
  await harness.tick();
  harness.transcriptSource.calls[0].reject(new ChatRateLimitedError(NOW_MS + 90_001));
  await flush();
  assert.deepEqual(harness.statuses.at(-1), [rateLimitedText(2), { canRetry: true }]);
  await harness.tick();
  assert.equal(harness.transcriptSource.calls.length, 1);
  harness.session.retry();
  await harness.tick();
  assert.deepEqual(harness.transcriptSource.calls.map((call) => call.index), [0, 0]);
});

test('fallback: retry re-schedules chunks that came back empty', async () => {
  const harness = sessionHarness({ overrides: { loadCues: noCaptionTracks, getDurationMs: () => 1_800_000 } });
  await harness.session.start();
  for (const positionMs of [0, 300_000, 600_000]) {
    harness.playback.positionMs = positionMs;
    await harness.tick();
    harness.transcriptSource.calls.at(-1).resolve([]);
    await flush();
  }
  assert.deepEqual(harness.statuses.at(-1), [STATUS_TEXTS.repeatedFailures, { canRetry: false }]);
  harness.session.retry();
  await harness.tick();
  assert.deepEqual(harness.transcriptSource.calls.map((call) => call.index), [0, 1, 2, 2]);
});

test('fallback without a known duration reports captionsNotFetched and starts no timer', async () => {
  const harness = sessionHarness({ overrides: { loadCues: noCaptionTracks, getDurationMs: () => 0 } });
  await harness.session.start();
  assert.deepEqual(harness.statuses.at(-1), [STATUS_TEXTS.captionsNotFetched, { canRetry: false }]);
  assert.equal(harness.timer.setCount, 0);
  assert.deepEqual(harness.viewCalls.at(-1), ['clear']);
});

test('fallback on a live stream (infinite duration) behaves like an unknown duration', async () => {
  const harness = sessionHarness({ overrides: { loadCues: noCaptionTracks, getDurationMs: () => Infinity } });
  await harness.session.start();
  assert.deepEqual(harness.statuses.at(-1), [STATUS_TEXTS.captionsNotFetched, { canRetry: false }]);
  assert.equal(harness.timer.setCount, 0);
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

/**
 * Harness for the wait-for-subtitles tests: the fake video flips `playback.isPaused` the way
 * a real <video> does, the clock is movable, and every pause or play call is recorded.
 */
function waitHarness({ overrides = {}, ...rest } = {}) {
  const clock = { nowMs: NOW_MS };
  const videoCalls = [];
  const harness = sessionHarness({
    ...rest,
    overrides: {
      isWaitForSubtitlesEnabled: () => true,
      now: () => clock.nowMs,
      pauseVideo: () => {
        videoCalls.push('pause');
        harness.playback.isPaused = true;
      },
      playVideo: () => {
        videoCalls.push('play');
        harness.playback.isPaused = false;
      },
      ...overrides,
    },
  });
  return { ...harness, clock, videoCalls };
}

test('waiting for a cue pauses the video once and does not resume it by itself', async () => {
  const harness = waitHarness();
  await harness.session.start();
  for (let tick = 0; tick < 3; tick += 1) await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause']);
});

test('the video resumes when the awaited cue is translated', async () => {
  const harness = waitHarness();
  await harness.session.start();
  await harness.tick();
  const { cues, resolve } = harness.translator.calls[0];
  resolve(allTranslated(cues));
  await flush();
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause', 'play']);
  assert.deepEqual(harness.viewCalls.at(-1), ['showCueText', 't0']);
});

test('the cap of 30 s plays the video and shows translationDelayed', async () => {
  const harness = waitHarness();
  await harness.session.start();
  await harness.tick();
  harness.clock.nowMs += 29_999;
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause']);
  harness.clock.nowMs += 1;
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause', 'play']);
  assert.deepEqual(harness.viewCalls.at(-1), ['showStatus', STATUS_TEXTS.translationDelayed]);
  assert.deepEqual(harness.statuses.at(-1), [STATUS_TEXTS.translationDelayed, { canRetry: false }]);
  // After the cap the video is never paused again for this wait.
  for (let tick = 0; tick < 3; tick += 1) await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause', 'play']);
});

test('after the cap, the translated cue replaces translationDelayed and the panel status clears', async () => {
  const harness = waitHarness();
  await harness.session.start();
  await harness.tick();
  harness.clock.nowMs += 30_000;
  await harness.tick();
  const { cues, resolve } = harness.translator.calls[0];
  resolve(allTranslated(cues));
  await flush();
  await harness.tick();
  assert.deepEqual(harness.viewCalls.at(-1), ['showCueText', 't0']);
  assert.deepEqual(harness.statuses.at(-1), [null, { canRetry: false }]);
  assert.deepEqual(harness.videoCalls, ['pause', 'play']);
});

test('an ad during our pause plays the video once', async () => {
  const harness = waitHarness();
  await harness.session.start();
  await harness.tick();
  harness.session.setAdPlaying(true);
  assert.deepEqual(harness.videoCalls, ['pause', 'play']);
  for (let tick = 0; tick < 3; tick += 1) await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause', 'play']);
  harness.session.setAdPlaying(false);
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause', 'play', 'pause']);
});

test('an ad does not call play when the video is already playing again', async () => {
  const harness = waitHarness();
  await harness.session.start();
  await harness.tick();
  harness.playback.isPaused = false; // the user pressed play
  harness.session.setAdPlaying(true);
  assert.deepEqual(harness.videoCalls, ['pause']);
});

test('a user pause is not resumed when the cue becomes ready', async () => {
  const harness = waitHarness({ cachedEntry: { translations: translationsOf([...Array(10).keys()]) } });
  await harness.session.start();
  harness.playback.isPaused = true; // the user's own pause on a translated cue
  harness.playback.positionMs = 5500;
  for (let tick = 0; tick < 3; tick += 1) await harness.tick();
  assert.deepEqual(harness.videoCalls, []);
});

test('a user pause made while the cue is waiting is never undone by us', async () => {
  const harness = waitHarness({ overrides: { pauseVideo: () => {} } });
  harness.playback.isPaused = true; // the user pauses first: we only observe a paused video
  await harness.session.start();
  await harness.tick();
  const { cues, resolve } = harness.translator.calls[0];
  resolve(allTranslated(cues));
  await flush();
  for (let tick = 0; tick < 3; tick += 1) await harness.tick();
  assert.deepEqual(harness.videoCalls, []);
  assert.equal(harness.playback.isPaused, true);
});

test('the user resuming over our pause drops the flag: the video is not paused or played again', async () => {
  const harness = waitHarness();
  await harness.session.start();
  await harness.tick();
  harness.playback.isPaused = false; // the user pressed play over our pause
  const { cues, resolve } = harness.translator.calls[0];
  resolve(allTranslated(cues));
  await flush();
  for (let tick = 0; tick < 3; tick += 1) await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause']);
});

test('seeking during the wait restarts the 30 s timer on the new position', async () => {
  const harness = waitHarness();
  await harness.session.start();
  await harness.tick();
  harness.clock.nowMs += 19_750;
  await harness.tick();
  harness.clock.nowMs += 250;
  harness.playback.positionMs = 6000; // seek to another untranslated cue
  await harness.tick();
  harness.clock.nowMs += 20_000; // 40 s after the first wait, 20 s after the seek
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause']);
  harness.clock.nowMs += 10_000;
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause', 'play']);
});

test('no pause is made at the end of the video', async () => {
  const harness = waitHarness({ overrides: { getDurationMs: () => 1000 } });
  harness.playback.positionMs = 1000;
  await harness.session.start();
  await harness.tick();
  assert.deepEqual(harness.videoCalls, []);
});

test('a throwing pauseVideo does not crash the tick and leaves no pause flag', async () => {
  let pauseCalls = 0;
  const harness = waitHarness({
    overrides: {
      pauseVideo: () => {
        pauseCalls += 1;
        throw new Error('x');
      },
    },
  });
  await harness.session.start();
  await harness.tick();
  await harness.tick();
  assert.equal(pauseCalls, 3); // start() ticks once, then two timer ticks: no stuck flag
  assert.deepEqual(harness.viewCalls.at(-1), ['showStatus', STATUS_TEXTS.translating]);
  assert.deepEqual(harness.videoCalls, []);
  const { cues, resolve } = harness.translator.calls[0];
  resolve(allTranslated(cues));
  await flush();
  await harness.tick();
  assert.deepEqual(harness.viewCalls.at(-1), ['showCueText', 't0']);
  assert.equal(pauseCalls, 3);
});

test('a throwing playVideo does not crash the tick and the pause flag is released', async () => {
  const harness = waitHarness({
    overrides: {
      playVideo: () => {
        harness.videoCalls.push('play');
        throw new Error('x');
      },
    },
  });
  await harness.session.start();
  await harness.tick();
  const { cues, resolve } = harness.translator.calls[0];
  resolve(allTranslated(cues));
  await flush();
  await harness.tick();
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause', 'play']); // not retried: the flag is released
  assert.deepEqual(harness.viewCalls.at(-1), ['showCueText', 't0']);
});

test('the setting off never pauses', async () => {
  const harness = waitHarness({ overrides: { isWaitForSubtitlesEnabled: () => false } });
  await harness.session.start();
  for (let tick = 0; tick < 3; tick += 1) await harness.tick();
  assert.deepEqual(harness.videoCalls, []);
});

test('switching the setting off during our pause resumes the video', async () => {
  let isEnabled = true;
  const harness = waitHarness({ overrides: { isWaitForSubtitlesEnabled: () => isEnabled } });
  await harness.session.start();
  await harness.tick();
  isEnabled = false;
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause', 'play']);
});

test('a gap between cues never pauses the video', async () => {
  const harness = waitHarness();
  harness.playback.positionMs = 950; // between cue 0 (ends 900) and cue 1 (starts 1000)
  await harness.session.start();
  await harness.tick();
  assert.deepEqual(harness.videoCalls, []);
});

test('stop() releases our pause so the video is not left paused', async () => {
  const harness = waitHarness();
  await harness.session.start();
  await harness.tick();
  harness.session.stop();
  assert.deepEqual(harness.videoCalls, ['pause', 'play']);
});

test('the user pressing play over our pause stops pausing for the rest of the wait', async () => {
  const harness = waitHarness();
  await harness.session.start();
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause']);
  harness.playback.isPaused = false; // the user pressed play; the cue is still untranslated
  for (let tick = 0; tick < 3; tick += 1) {
    harness.clock.nowMs += 250;
    harness.playback.positionMs += 250;
    await harness.tick();
  }
  assert.deepEqual(harness.videoCalls, ['pause']);
  assert.deepEqual(harness.viewCalls.at(-1), ['showStatus', STATUS_TEXTS.translating]);
});

test('after the user dismissed the wait, a seek to another untranslated cue pauses again', async () => {
  const harness = waitHarness();
  await harness.session.start();
  await harness.tick();
  harness.playback.isPaused = false;
  await harness.tick();
  harness.playback.positionMs = 6000;
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause', 'pause']);
});

test('the end of the video lifts our pause', async () => {
  const harness = waitHarness({ overrides: { getDurationMs: () => 5000 } });
  await harness.session.start();
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause']);
  harness.playback.positionMs = 5000;
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause', 'play']);
});

test('a small position step after a stall is not a seek: the cap stays and no pause is set', async () => {
  const harness = waitHarness();
  await harness.session.start();
  await harness.tick();
  harness.clock.nowMs += 30_000;
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause', 'play']);
  harness.clock.nowMs += 250;
  harness.playback.positionMs += 2500; // a hiccup: 2500 ms of video in 250 ms of real time
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause', 'play']);
  assert.deepEqual(harness.viewCalls.at(-1), ['showStatus', STATUS_TEXTS.translationDelayed]);
});

test('a small step back of the position is not a seek: the dismissed wait stays dismissed', async () => {
  const harness = waitHarness();
  await harness.session.start();
  await harness.tick();
  harness.playback.isPaused = false; // the user pressed play over our pause
  harness.clock.nowMs += 250;
  await harness.tick();
  harness.clock.nowMs += 250;
  harness.playback.positionMs -= 200; // the browser rounds currentTime back a little
  await harness.tick();
  harness.playback.positionMs += 100;
  harness.clock.nowMs += 250;
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause']);
});

test('a small step back of the position keeps the cap', async () => {
  const harness = waitHarness();
  harness.playback.positionMs = 500;
  await harness.session.start();
  await harness.tick();
  harness.clock.nowMs += 30_000;
  await harness.tick();
  harness.clock.nowMs += 250;
  harness.playback.positionMs -= 200;
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause', 'play']);
  assert.deepEqual(harness.viewCalls.at(-1), ['showStatus', STATUS_TEXTS.translationDelayed]);
});

test('a step back of 1000 ms is a seek: the dismissed wait pauses again', async () => {
  const harness = waitHarness();
  harness.playback.positionMs = 2500;
  await harness.session.start();
  await harness.tick();
  harness.playback.isPaused = false;
  harness.clock.nowMs += 250;
  await harness.tick();
  harness.clock.nowMs += 250;
  harness.playback.positionMs -= 1000; // lands on another untranslated cue
  await harness.tick();
  assert.deepEqual(harness.videoCalls, ['pause', 'pause']);
});

test('shows the translating status in the language of the texts option, Russian by default', async () => {
  const english = sessionHarness({ overrides: { texts: uiTexts('en') } });
  await english.session.start();
  english.playback.positionMs = 500;
  await english.tick();
  assert.deepEqual(english.viewCalls.at(-1), ['showStatus', uiTexts('en').translating]);
  assert.notEqual(uiTexts('en').translating, STATUS_TEXTS.translating);

  const byDefault = sessionHarness();
  await byDefault.session.start();
  byDefault.playback.positionMs = 500;
  await byDefault.tick();
  assert.deepEqual(byDefault.viewCalls.at(-1), ['showStatus', STATUS_TEXTS.translating]);
});
