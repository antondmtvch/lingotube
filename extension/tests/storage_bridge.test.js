import { test } from 'node:test';
import assert from 'node:assert/strict';
import { startStorageHost } from '../src/content/storage_host.js';
import { createExtensionStorage } from '../src/page/extension_storage.js';

function createFakeWindow() {
  const fakeWindow = new EventTarget();
  fakeWindow.postMessage = (data) => {
    queueMicrotask(() => {
      const event = new Event('message');
      event.data = data;
      event.source = fakeWindow;
      fakeWindow.dispatchEvent(event);
    });
  };
  return fakeWindow;
}

function createMapStorageArea() {
  const items = new Map();
  return {
    async get(keys) {
      return Object.fromEntries(keys.filter((key) => items.has(key)).map((key) => [key, items.get(key)]));
    },
    async set(newItems) {
      for (const [key, value] of Object.entries(newItems)) items.set(key, value);
    },
    async remove(keys) {
      for (const key of keys) items.delete(key);
    },
  };
}

function dispatchRawMessage(fakeWindow, data, source) {
  const event = new Event('message');
  event.data = data;
  event.source = source;
  fakeWindow.dispatchEvent(event);
}

test('set then get round-trips through host and client', async () => {
  const fakeWindow = createFakeWindow();
  startStorageHost({ window: fakeWindow, storageArea: createMapStorageArea() });
  const storage = createExtensionStorage({ window: fakeWindow });
  await storage.set({ a: 1, b: 'x' });
  assert.deepEqual(await storage.get(['a', 'b', 'c']), { a: 1, b: 'x' });
  await storage.remove(['a']);
  assert.deepEqual(await storage.get(['a', 'b']), { b: 'x' });
});

test('host ignores messages on other channels and from other sources', async () => {
  const fakeWindow = createFakeWindow();
  let storageCalls = 0;
  const storageArea = {
    get: async () => {
      storageCalls++;
      return {};
    },
  };
  startStorageHost({ window: fakeWindow, storageArea });

  const request = { kind: 'request', requestId: 1, operation: 'get', payload: { keys: [] } };
  dispatchRawMessage(fakeWindow, { channel: 'other', ...request }, fakeWindow);
  dispatchRawMessage(fakeWindow, { channel: 'lingotube-storage', ...request }, {});

  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(storageCalls, 0);
});

test('client rejects after timeoutMs when nobody answers', async () => {
  const storage = createExtensionStorage({ window: createFakeWindow(), timeoutMs: 20 });
  await assert.rejects(storage.get(['a']), { message: 'extension storage did not answer' });
});

test('host reports a storage failure as errorText without throwing', async () => {
  const fakeWindow = createFakeWindow();
  const storageArea = createMapStorageArea();
  storageArea.set = async () => {
    throw new Error('QUOTA_BYTES');
  };
  startStorageHost({ window: fakeWindow, storageArea });
  const storage = createExtensionStorage({ window: fakeWindow });
  await assert.rejects(storage.set({ a: 1 }), { message: 'QUOTA_BYTES' });
});
