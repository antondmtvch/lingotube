import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CueTrack } from '../src/shared/cue_track.js';
import { TranslationPump } from '../src/shared/translation_pump.js';
import {
  ChatRateLimitedError,
  ChatRequestFailedError,
  ChatUnavailableError,
  NotSignedInError,
} from '../src/shared/chat_errors.js';

function trackOfCues(count) {
  const cues = [];
  for (let id = 0; id < count; id += 1) {
    cues.push({ id, startMs: id * 1000, endMs: id * 1000 + 900, sourceText: `source ${id}` });
  }
  return new CueTrack(cues);
}

/** Fake translator: every call waits for the test to settle it. */
function controllableTranslator() {
  const calls = [];
  return {
    calls,
    async translateCues(cues) {
      return new Promise((resolve, reject) => calls.push({ cues, resolve, reject }));
    },
  };
}

function allTranslated(cues) {
  return {
    translationsByCueId: new Map(cues.map((cue) => [cue.id, `t${cue.id}`])),
    failedCueIds: [],
  };
}

function allFailed(cues) {
  return { translationsByCueId: new Map(), failedCueIds: cues.map((cue) => cue.id) };
}

function makePump({ track = trackOfCues(1000), translator = controllableTranslator(), position = { ms: 0 } } = {}) {
  const events = { changed: 0, stopped: [] };
  const pump = new TranslationPump({
    track,
    translator,
    getPositionMs: () => position.ms,
    onTranslationsChanged: () => {
      events.changed += 1;
    },
    onStopped: (reason) => events.stopped.push(reason),
  });
  return { pump, track, translator, position, events };
}

/** Runs a tick whose request is settled by `settle(call)`. */
async function tickAndSettle(pump, translator, settle) {
  const tickPromise = pump.tick();
  await Promise.resolve();
  settle(translator.calls[translator.calls.length - 1]);
  await tickPromise;
}

test('one request at a time: a second tick during a request sends nothing', async () => {
  const { pump, translator } = makePump();
  const first = pump.tick();
  await pump.tick();
  assert.equal(translator.calls.length, 1);
  translator.calls[0].resolve(allTranslated(translator.calls[0].cues));
  await first;
});

test('a batch is marked pending while the request runs and applied afterwards', async () => {
  const { pump, track, translator, events } = makePump();
  const first = pump.tick();
  assert.equal(track.translationState(0), 'pending');
  translator.calls[0].resolve(allTranslated(translator.calls[0].cues));
  await first;
  assert.equal(track.translationState(0), 'done');
  assert.equal(events.changed, 1);
});

test('failed cues of a reply are marked failed', async () => {
  const { pump, track, translator } = makePump();
  await tickAndSettle(pump, translator, (call) =>
    call.resolve({ translationsByCueId: new Map([[0, 'a']]), failedCueIds: [1] }),
  );
  assert.equal(track.translationState(0), 'done');
  assert.equal(track.translationState(1), 'failed');
});

test('a seek during a request: the reply is still applied, the next batch starts at the new position', async () => {
  const { pump, track, translator, position } = makePump();
  const first = pump.tick();
  position.ms = 500000;
  translator.calls[0].resolve(allTranslated(translator.calls[0].cues));
  await first;
  assert.equal(track.translationState(0), 'done');
  const second = pump.tick();
  assert.equal(translator.calls[1].cues[0].id, 500);
  translator.calls[1].resolve(allTranslated(translator.calls[1].cues));
  await second;
});

test('nothing is requested while the reserve ahead is full', async () => {
  const track = trackOfCues(400);
  for (let id = 0; id < 200; id += 1) track.setTranslation(id, 't');
  const { pump, translator } = makePump({ track });
  await pump.tick();
  assert.equal(translator.calls.length, 0);
});

test('three failed messages in a row stop the pump with repeated-failures', async () => {
  const { pump, translator, events } = makePump();
  await tickAndSettle(pump, translator, (call) => call.reject(new ChatRequestFailedError()));
  await tickAndSettle(pump, translator, (call) => call.resolve(allFailed(call.cues)));
  assert.equal(pump.stopReason, null);
  await tickAndSettle(pump, translator, (call) => call.reject(new ChatRequestFailedError()));
  assert.equal(pump.stopReason, 'repeated-failures');
  assert.deepEqual(events.stopped, ['repeated-failures']);
  await pump.tick();
  assert.equal(translator.calls.length, 3);
});

test('a success between failures resets the count', async () => {
  const { pump, translator } = makePump();
  await tickAndSettle(pump, translator, (call) => call.reject(new ChatRequestFailedError()));
  await tickAndSettle(pump, translator, (call) => call.reject(new ChatRequestFailedError()));
  await tickAndSettle(pump, translator, (call) =>
    call.resolve({ translationsByCueId: new Map([[call.cues[0].id, 'a']]), failedCueIds: [] }),
  );
  await tickAndSettle(pump, translator, (call) => call.reject(new ChatRequestFailedError()));
  await tickAndSettle(pump, translator, (call) => call.reject(new ChatRequestFailedError()));
  assert.equal(pump.stopReason, null);
});

const immediateStopCases = [
  ['rate limit', () => new ChatRateLimitedError(Date.now() + 600000), 'rate-limited'],
  ['sign-in', () => new NotSignedInError(), 'not-signed-in'],
  ['unavailable', () => new ChatUnavailableError(), 'chat-unavailable'],
];

for (const [name, makeError, reason] of immediateStopCases) {
  test(`${name} error stops at once with ${reason}`, async () => {
    const { pump, translator, events } = makePump();
    await tickAndSettle(pump, translator, (call) => call.reject(makeError()));
    assert.equal(pump.stopReason, reason);
    assert.deepEqual(events.stopped, [reason]);
    await pump.tick();
    assert.equal(translator.calls.length, 1);
  });
}

test('after stop() a late reply changes nothing and calls no callback', async () => {
  const { pump, track, translator, events } = makePump();
  const first = pump.tick();
  pump.stop();
  translator.calls[0].resolve(allTranslated(translator.calls[0].cues));
  await first;
  assert.equal(track.translationState(0), 'pending');
  assert.equal(events.changed, 0);
  assert.deepEqual(events.stopped, []);
  assert.equal(pump.stopReason, null);
});

test('after stop() a late error changes nothing and calls no callback', async () => {
  const { pump, translator, events } = makePump();
  const first = pump.tick();
  pump.stop();
  translator.calls[0].reject(new ChatRateLimitedError(Date.now()));
  await first;
  assert.deepEqual(events.stopped, []);
  assert.equal(pump.stopReason, null);
});

test('a stopped pump sends nothing', async () => {
  const { pump, translator } = makePump();
  pump.stop();
  await pump.tick();
  assert.equal(translator.calls.length, 0);
});

test('pending cues return to none when the message throws', async () => {
  const { pump, track, translator } = makePump();
  await tickAndSettle(pump, translator, (call) => call.reject(new ChatRequestFailedError()));
  assert.equal(track.translationState(0), 'none');
  assert.equal(track.translationState(29), 'none');
});

test('resume after a rate-limited stop lets ticks run again', async () => {
  const { pump, translator } = makePump();
  await tickAndSettle(pump, translator, (call) => call.reject(new ChatRateLimitedError(Date.now())));
  assert.equal(pump.stopReason, 'rate-limited');
  pump.resume();
  assert.equal(pump.stopReason, null);
  await tickAndSettle(pump, translator, (call) => call.resolve(allTranslated(call.cues)));
  assert.equal(translator.calls.length, 2);
});

test('resume clears the failure counter', async () => {
  const { pump, translator } = makePump();
  for (let index = 0; index < 3; index += 1) {
    await tickAndSettle(pump, translator, (call) => call.reject(new ChatRequestFailedError()));
  }
  assert.equal(pump.stopReason, 'repeated-failures');
  pump.resume();
  await tickAndSettle(pump, translator, (call) => call.reject(new ChatRequestFailedError()));
  assert.equal(pump.stopReason, null);
});

test('resume after an owner stop() does nothing', async () => {
  const { pump, translator } = makePump();
  pump.stop();
  pump.resume();
  await pump.tick();
  assert.equal(translator.calls.length, 0);
});
