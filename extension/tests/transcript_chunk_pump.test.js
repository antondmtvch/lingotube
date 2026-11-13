import { test } from 'node:test';
import assert from 'node:assert/strict';
import { TranscriptChunkPump } from '../src/shared/transcript_chunk_pump.js';
import { TranscriptChunkStore } from '../src/shared/transcript_chunks.js';
import {
  ChatRateLimitedError,
  ChatRequestFailedError,
  ChatUnavailableError,
  NotSignedInError,
} from '../src/shared/chat_errors.js';

const flush = () => new Promise((resolve) => setImmediate(resolve));

/** Fake transcript source: every request waits for the test to settle it. */
function controllableSource() {
  const calls = [];
  return { calls, requestChunk: (index) => new Promise((resolve, reject) => calls.push({ index, resolve, reject })) };
}

function makePump({ durationMs = 1800000, position = { ms: 0 } } = {}) {
  const store = new TranscriptChunkStore(durationMs);
  const source = controllableSource();
  const events = { changed: 0, stopped: [] };
  const pump = new TranscriptChunkPump({
    store,
    source,
    getPositionMs: () => position.ms,
    onChunksChanged: () => {
      events.changed += 1;
    },
    onStopped: (reason) => events.stopped.push(reason),
  });
  return { pump, store, source, position, events };
}

const linesOf = (index) => [{ startMs: index * 300000 + 1000, endMs: index * 300000 + 3000, text: `chunk ${index}` }];

test('the chunk under the playhead is requested first, one request at a time', async () => {
  const { pump, store, source, position, events } = makePump({ position: { ms: 620000 } });
  pump.tick();
  pump.tick();
  await flush();
  assert.deepEqual(source.calls.map((call) => call.index), [2]);
  source.calls[0].resolve(linesOf(2));
  await flush();
  assert.equal(store.hasChunk(2), true);
  assert.equal(events.changed, 1);
  position.ms = 850000;
  pump.tick();
  await flush();
  assert.deepEqual(source.calls.map((call) => call.index), [2, 3]);
});

test('a chunk with no lines is failed and counted; three failures in a row stop the pump', async () => {
  const { pump, store, source, position, events } = makePump();
  pump.tick();
  await flush();
  source.calls[0].resolve([]);
  await flush();
  assert.deepEqual(store.displayAt(1000), { kind: 'failed' });
  // A thrown request failure counts too, and the same chunk is asked again on the next tick.
  position.ms = 300000;
  pump.tick();
  await flush();
  source.calls[1].reject(new ChatRequestFailedError());
  await flush();
  assert.deepEqual(events.stopped, []);
  pump.tick();
  await flush();
  assert.equal(source.calls[2].index, 1);
  source.calls[2].reject(new ChatRequestFailedError());
  await flush();
  assert.deepEqual(events.stopped, ['repeated-failures']);
  assert.equal(pump.stopReason, 'repeated-failures');
  pump.tick();
  await flush();
  assert.equal(source.calls.length, 3);
});

test('a loaded chunk resets the failure count', async () => {
  const { pump, source, position, events } = makePump();
  for (const [index, settle] of [[0, (call) => call.resolve([])], [1, (call) => call.resolve([])], [2, (call) => call.resolve(linesOf(2))], [3, (call) => call.resolve([])], [4, (call) => call.resolve([])]]) {
    position.ms = index * 300000;
    pump.tick();
    await flush();
    settle(source.calls.at(-1));
    await flush();
  }
  assert.deepEqual(events.stopped, []);
});

test('when every chunk of the video failed the pump stops with no-speech', async () => {
  const { pump, source, position, events } = makePump({ durationMs: 400000 });
  pump.tick();
  await flush();
  source.calls[0].resolve([]);
  await flush();
  position.ms = 250000;
  pump.tick();
  await flush();
  assert.equal(source.calls[1].index, 1);
  source.calls[1].resolve([]);
  await flush();
  assert.deepEqual(events.stopped, ['no-speech']);
});

test('chat errors that stop requests map to the same stop reasons as the translation pump', async () => {
  for (const [error, reason] of [
    [new ChatRateLimitedError(5), 'rate-limited'],
    [new NotSignedInError(), 'not-signed-in'],
    [new ChatUnavailableError(), 'chat-unavailable'],
  ]) {
    const { pump, store, source, events } = makePump();
    pump.tick();
    await flush();
    source.calls[0].reject(error);
    await flush();
    assert.deepEqual(events.stopped, [reason]);
    // The chunk is not failed: it is asked again after resume().
    assert.deepEqual(store.displayAt(1000), { kind: 'waiting' });
    pump.resume();
    pump.tick();
    await flush();
    assert.deepEqual(source.calls.map((call) => call.index), [0, 0]);
  }
});

test('a late chunk reply after stop() changes nothing', async () => {
  const { pump, store, source, events } = makePump();
  pump.tick();
  await flush();
  pump.stop();
  source.calls[0].resolve(linesOf(0));
  await flush();
  assert.equal(store.hasChunk(0), false);
  assert.equal(events.changed, 0);
  pump.resume();
  pump.tick();
  await flush();
  assert.equal(source.calls.length, 1);
});
