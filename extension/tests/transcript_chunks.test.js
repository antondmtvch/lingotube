import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  CHUNK_MS,
  TranscriptChunkStore,
  chunkBounds,
  linesInsideChunk,
} from '../src/shared/transcript_chunks.js';

const cue = (startMs, endMs, text) => ({ startMs, endMs, text });

test('chunks are five minutes long; the last one ends with the video', () => {
  assert.equal(CHUNK_MS, 300000);
  assert.deepEqual(chunkBounds(0, 700000), { startMs: 0, endMs: 300000 });
  assert.deepEqual(chunkBounds(2, 700000), { startMs: 600000, endMs: 700000 });
  const store = new TranscriptChunkStore(700000);
  assert.equal(store.chunkCount, 3);
  assert.equal(store.chunkIndexAt(620000), 2);
});

test('the chunk under the playhead is requested first, not chunk 0', () => {
  const store = new TranscriptChunkStore(1800000);
  assert.equal(store.nextChunkToRequest(620000), 2);
});

test('the next chunk is requested when under 120000 ms remain in the current one', () => {
  const store = new TranscriptChunkStore(1800000);
  store.addChunk(0, [cue(1000, 2000, 'a')]);
  assert.equal(store.nextChunkToRequest(100000), null); // 200 s remain
  assert.equal(store.nextChunkToRequest(180000), null); // exactly 120 s remain
  assert.equal(store.nextChunkToRequest(180001), 1);
  assert.equal(store.nextChunkToRequest(250000, 30000), null);
  store.addChunk(1, [cue(301000, 302000, 'b')]);
  assert.equal(store.nextChunkToRequest(290000), null);
});

test('nothing is requested past the end of the video or for a failed chunk', () => {
  const store = new TranscriptChunkStore(600000);
  assert.equal(store.nextChunkToRequest(600000), null);
  assert.equal(store.nextChunkToRequest(900000), null);
  store.markChunkFailed(0);
  assert.equal(store.nextChunkToRequest(10000), null);
  // A failed current chunk does not block the next one when the playhead nears it.
  assert.equal(store.nextChunkToRequest(200000), 1);
  store.markChunkFailed(1);
  assert.equal(store.nextChunkToRequest(200000), null);
  assert.equal(store.nextChunkToRequest(590000), null); // the last chunk has no next one
  assert.equal(store.areAllChunksFailed(), true);
  store.resetFailed();
  assert.equal(store.nextChunkToRequest(10000), 0);
  assert.equal(store.areAllChunksFailed(), false);
});

test('displayAt is waiting inside a missing chunk and nothing in a gap of a loaded one', () => {
  const store = new TranscriptChunkStore(900000);
  store.addChunk(0, [cue(1000, 3000, 'Привет'), cue(5000, 6000, 'Пока')]);
  assert.deepEqual(store.displayAt(2000), { kind: 'text', text: 'Привет' });
  assert.deepEqual(store.displayAt(4000), { kind: 'nothing' });
  assert.deepEqual(store.displayAt(5500), { kind: 'text', text: 'Пока' });
  assert.deepEqual(store.displayAt(400000), { kind: 'waiting' });
  store.markChunkFailed(2);
  assert.deepEqual(store.displayAt(700000), { kind: 'failed' });
  assert.deepEqual(store.displayAt(900000), { kind: 'nothing' });
});

test('a chunk keeps its cues inside its own bounds', () => {
  const store = new TranscriptChunkStore(900000);
  store.addChunk(1, [cue(290000, 295000, 'before'), cue(299000, 302000, 'cut start'), cue(598000, 610000, 'long'), cue(600000, 601000, 'after')]);
  assert.deepEqual(store.toCacheEntry(), { chunks: { 1: [cue(598000, 600000, 'long')] } });
  assert.equal(store.hasChunk(1), true);
  assert.equal(store.hasChunk(0), false);
});

test('linesInsideChunk keeps absolute times and shifts chunk-relative ones', () => {
  const bounds = { startMs: 300000, endMs: 600000 };
  // Absolute video times, as the CLI sees them: kept; lines outside the chunk are dropped.
  assert.deepEqual(
    linesInsideChunk([cue(299000, null, 'old'), cue(301000, null, 'a'), cue(600000, null, 'next')], bounds),
    [cue(301000, null, 'a')],
  );
  // Every line before the chunk start: the chat counted from the chunk start.
  assert.deepEqual(
    linesInsideChunk([cue(1000, null, 'a'), cue(5000, 9000, 'b')], bounds),
    [cue(301000, null, 'a'), cue(305000, 309000, 'b')],
  );
  assert.deepEqual(linesInsideChunk([cue(1000, null, 'a')], { startMs: 0, endMs: 300000 }), [cue(1000, null, 'a')]);
});

test('the chunk cache entry round-trips', () => {
  const store = new TranscriptChunkStore(900000);
  store.addChunk(0, [cue(1000, 3000, 'a')]);
  store.addChunk(2, [cue(610000, 612000, 'c')]);
  const entry = JSON.parse(JSON.stringify(store.toCacheEntry()));
  assert.deepEqual(entry, { chunks: { 0: [cue(1000, 3000, 'a')], 2: [cue(610000, 612000, 'c')] } });

  const restored = new TranscriptChunkStore(900000);
  assert.equal(restored.loadCacheEntry(entry), 2);
  assert.deepEqual(restored.displayAt(2000), { kind: 'text', text: 'a' });
  assert.deepEqual(restored.displayAt(611000), { kind: 'text', text: 'c' });
  assert.deepEqual(restored.displayAt(400000), { kind: 'waiting' });
});

test('malformed chunks of a cache entry are skipped, well-formed ones kept', () => {
  const store = new TranscriptChunkStore(900000);
  const loaded = store.loadCacheEntry({
    chunks: {
      0: [cue(1000, 3000, 'good')],
      1: [cue(301000, Number.NaN, 'bad end')],
      2: [{ startMs: 601000, endMs: 602000, text: 5 }],
      3: [cue(901000, 902000, 'past the end')],
      x: [cue(1000, 2000, 'bad index')],
      4: 'not a list',
    },
  });
  assert.equal(loaded, 1);
  assert.deepEqual(Object.keys(store.toCacheEntry().chunks), ['0']);
  for (const entry of [null, 'x', { translations: {} }, { chunks: [] }, { chunks: { 0: [] } }]) {
    assert.equal(new TranscriptChunkStore(900000).loadCacheEntry(entry), 0);
  }
});
