import { test } from 'node:test';
import assert from 'node:assert/strict';
import { TranslationCache } from '../src/page/translation_cache.js';
import { createExtensionStorage } from '../src/page/extension_storage.js';

function fakeStorage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    get: async (keys) => Object.fromEntries(keys.filter((key) => data.has(key)).map((key) => [key, data.get(key)])),
    set: async (items) => { for (const [key, value] of Object.entries(items)) data.set(key, value); },
    remove: async (keys) => { for (const key of keys) data.delete(key); },
  };
}

function entryOfSize(size) {
  return { translations: { 0: 'x'.repeat(size) } };
}
const sizeOf = (entry) => JSON.stringify(entry).length;

test('cache: save then load returns the entry', async () => {
  const cache = new TranslationCache(fakeStorage());
  await cache.save('cache:v1', { translations: { 0: 'привет' } });
  assert.deepEqual(await cache.load('cache:v1'), { translations: { 0: 'привет' } });
  assert.equal(await cache.load('cache:missing'), null);
});

test('cache: the oldest entry is evicted when the total would exceed maxTotalBytes', async () => {
  const storage = fakeStorage();
  let time = 0;
  const entry = entryOfSize(60);
  const cache = new TranslationCache(storage, { maxTotalBytes: sizeOf(entry) * 2 + 10, now: () => ++time });
  await cache.save('cache:a', entry);
  await cache.save('cache:b', entry);
  await cache.save('cache:c', entry);
  assert.equal(await cache.load('cache:a'), null);
  assert.deepEqual(await cache.load('cache:b'), entry);
  assert.deepEqual(await cache.load('cache:c'), entry);
  assert.ok(!storage.data.has('cache:a'));
  assert.deepEqual(storage.data.get('cacheIndex').map((item) => item.key), ['cache:b', 'cache:c']);
});

test('cache: an entry larger than maxTotalBytes is not stored and nothing else is evicted', async () => {
  const cache = new TranslationCache(fakeStorage(), { maxTotalBytes: 300 });
  await cache.save('cache:small', entryOfSize(50));
  await cache.save('cache:huge', entryOfSize(500));
  assert.equal(await cache.load('cache:huge'), null);
  assert.deepEqual(await cache.load('cache:small'), entryOfSize(50));
});

test('cache: saving the same key again replaces it without double counting', async () => {
  const entry = entryOfSize(60);
  const storage = fakeStorage();
  const cache = new TranslationCache(storage, { maxTotalBytes: sizeOf(entry) + 10 });
  await cache.save('cache:a', entry);
  await cache.save('cache:a', { translations: { 0: 'y'.repeat(60) } });
  assert.deepEqual(await cache.load('cache:a'), { translations: { 0: 'y'.repeat(60) } });
  assert.deepEqual(storage.data.get('cacheIndex').map((item) => item.key), ['cache:a']);
});

test('cache: overlapping saves are serialized, so every entry reaches the index and the accounting', async () => {
  const storage = fakeStorage();
  const pause = () => new Promise((resolve) => setTimeout(resolve, 5));
  const yielding = {
    get: async (keys) => { const result = await storage.get(keys); await pause(); return result; },
    set: async (items) => { await pause(); return storage.set(items); },
    remove: (keys) => storage.remove(keys),
  };
  const entry = entryOfSize(60);
  const cache = new TranslationCache(yielding, { maxTotalBytes: sizeOf(entry) * 2 + 10 });
  await Promise.all([cache.save('cache:a', entry), cache.save('cache:b', entry), cache.save('cache:c', entry)]);
  assert.deepEqual(storage.data.get('cacheIndex').map((item) => item.key), ['cache:b', 'cache:c']);
  assert.ok(!storage.data.has('cache:a'));
});

test('cache: malformed stored entries load as null', async () => {
  const bad = [
    'text', 5, null, [], {}, { translations: 'x' }, { translations: [] }, { translations: null },
    { translations: { 0: 5 } }, { translations: { 0: 'ok', 1: null } }, { translations: { 0: { a: 1 } } },
  ];
  const initial = {};
  bad.forEach((value, index) => { initial[`cache:${index}`] = value; });
  const cache = new TranslationCache(fakeStorage(initial));
  for (let index = 0; index < bad.length; index += 1) assert.equal(await cache.load(`cache:${index}`), null);
});

test('cache: a garbage index does not break save', async () => {
  const cache = new TranslationCache(fakeStorage({ cacheIndex: 'garbage' }));
  await cache.save('cache:a', { translations: { 0: 'a' } });
  assert.deepEqual(await cache.load('cache:a'), { translations: { 0: 'a' } });
});

test('cache: storage that rejects (quota) → save resolves, load resolves null', async () => {
  const failing = {
    get: async () => { throw new Error('quota'); },
    set: async () => { throw new Error('QUOTA_BYTES quota exceeded'); },
    remove: async () => { throw new Error('quota'); },
  };
  const cache = new TranslationCache(failing);
  await cache.save('cache:a', { translations: { 0: 'a' } });
  assert.equal(await cache.load('cache:a'), null);
});

test('cache: storage that never answers → load resolves null after the bridge timeout', async () => {
  const silentWindow = { addEventListener() {}, removeEventListener() {}, postMessage() {} };
  const cache = new TranslationCache(createExtensionStorage({ window: silentWindow, timeoutMs: 20 }));
  assert.equal(await cache.load('cache:a'), null);
  await cache.save('cache:a', { translations: { 0: 'a' } });
});

test('cache: a chat transcript entry {chunks} is saved and loaded', async () => {
  const cache = new TranslationCache(fakeStorage());
  const entry = { chunks: { 0: [{ startMs: 1000, endMs: 2500, text: 'привет' }], 3: [{ startMs: 901000, endMs: 903000, text: 'b' }] } };
  await cache.save('cache:chat', entry);
  assert.deepEqual(await cache.load('cache:chat'), entry);
});

test('cache: malformed chunk entries load as null and are not saved', async () => {
  const bad = [
    { chunks: 'x' }, { chunks: [] }, { chunks: null }, { chunks: { 0: 'x' } }, { chunks: { 0: [null] } },
    { chunks: { 0: [{ startMs: 1, endMs: 2 }] } }, { chunks: { 0: [{ startMs: 'a', endMs: 2, text: 't' }] } },
    { chunks: { 0: [{ startMs: 1, endMs: Infinity, text: 't' }] } }, { chunks: { x: [{ startMs: 1, endMs: 2, text: 't' }] } },
  ];
  const initial = {};
  bad.forEach((value, index) => { initial[`cache:${index}`] = value; });
  const storage = fakeStorage(initial);
  const cache = new TranslationCache(storage);
  for (let index = 0; index < bad.length; index += 1) assert.equal(await cache.load(`cache:${index}`), null, String(index));
  await cache.save('cache:new', bad[4]);
  assert.ok(!storage.data.has('cache:new'));
});
