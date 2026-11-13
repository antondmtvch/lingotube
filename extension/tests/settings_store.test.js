import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_SETTINGS, SettingsStore } from '../src/page/settings_store.js';

/** In-memory stand-in for the extension storage client. */
function fakeStorage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    get: async (keys) => Object.fromEntries(keys.filter((key) => data.has(key)).map((key) => [key, data.get(key)])),
    set: async (items) => { for (const [key, value] of Object.entries(items)) data.set(key, value); },
    remove: async (keys) => { for (const key of keys) data.delete(key); },
  };
}

test('defaults are as documented', () => {
  assert.deepEqual(DEFAULT_SETTINGS, {
    enabled: false, language: { code: 'ru', name: 'Russian' }, customLanguageNames: [], textScale: 1, overlayPosition: null,
  });
});

test('settings: nothing stored loads as defaults', async () => {
  assert.deepEqual(await new SettingsStore(fakeStorage()).load(), DEFAULT_SETTINGS);
});

test('settings: garbage in storage loads as defaults', async () => {
  const garbageValues = [
    'text', 42, null, [],
    { enabled: 'yes', language: 5, customLanguageNames: 'x', textScale: 'big', overlayPosition: 7 },
  ];
  for (const garbage of garbageValues) {
    assert.deepEqual(await new SettingsStore(fakeStorage({ settings: garbage })).load(), DEFAULT_SETTINGS);
  }
});

test('settings: a stored typed language with an empty name falls back to the default language', async () => {
  const storage = fakeStorage({ settings: { language: { code: 'custom', name: '   ' } } });
  assert.deepEqual((await new SettingsStore(storage).load()).language, DEFAULT_SETTINGS.language);
});

test('settings: textScale is clamped to 0.6..2.0', async () => {
  const store = new SettingsStore(fakeStorage());
  assert.equal((await store.save({ textScale: 5 })).textScale, 2);
  assert.equal((await store.save({ textScale: 0.1 })).textScale, 0.6);
  assert.equal((await store.save({ textScale: 1.5 })).textScale, 1.5);
});

test('settings: save merges changes and persists them', async () => {
  const storage = fakeStorage();
  const store = new SettingsStore(storage);
  await store.save({ enabled: true });
  await store.save({ overlayPosition: { x: 0.5, y: 0.25 }, language: { code: 'ja', name: 'Japanese' } });
  const loaded = await new SettingsStore(storage).load();
  assert.equal(loaded.enabled, true);
  assert.deepEqual(loaded.overlayPosition, { x: 0.5, y: 0.25 });
  assert.deepEqual(loaded.language, { code: 'ja', name: 'Japanese' });
});

test('settings: saving a sixth custom language drops the oldest', async () => {
  const store = new SettingsStore(fakeStorage());
  let settings = DEFAULT_SETTINGS;
  for (const name of ['a', 'b', 'c', 'd', 'e', 'f']) {
    settings = await store.save({ customLanguageNames: [name, ...settings.customLanguageNames] });
  }
  assert.deepEqual(settings.customLanguageNames, ['f', 'e', 'd', 'c', 'b']);
});

test('settings: custom names have no duplicates (newest kept) and no empty names', async () => {
  const store = new SettingsStore(fakeStorage());
  const settings = await store.save({ customLanguageNames: ['татарский', ' ', 'Татарский ', 'Latin'] });
  assert.deepEqual(settings.customLanguageNames, ['татарский', 'Latin']);
});
