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
  const storage = fakeStorage({ settings: { language: { code: null, name: '   ' } } });
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
  await store.save({ overlayPosition: { centerXFraction: 0.5, bottomYFraction: 0.25 }, language: { code: 'ja', name: 'Japanese' } });
  const loaded = await new SettingsStore(storage).load();
  assert.equal(loaded.enabled, true);
  assert.deepEqual(loaded.overlayPosition, { centerXFraction: 0.5, bottomYFraction: 0.25 });
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

test('settings: overlayPosition keeps {centerXFraction, bottomYFraction} in [0, 1] and drops everything else', async () => {
  const valid = { centerXFraction: 0, bottomYFraction: 1 };
  const invalidPositions = [
    { x: 0.5, y: 0.25 }, { centerXFraction: 1.5, bottomYFraction: 0.5 }, { centerXFraction: 0.5, bottomYFraction: -0.1 },
    { centerXFraction: NaN, bottomYFraction: 0.5 }, { centerXFraction: 0.5, bottomYFraction: Infinity },
    { centerXFraction: '0.5', bottomYFraction: '0.5' }, { centerXFraction: 0.5 },
  ];
  assert.deepEqual((await new SettingsStore(fakeStorage({ settings: { overlayPosition: valid } })).load()).overlayPosition, valid);
  for (const overlayPosition of invalidPositions) {
    const loaded = await new SettingsStore(fakeStorage({ settings: { overlayPosition } })).load();
    assert.equal(loaded.overlayPosition, null);
  }
});

test('settings: a typed language ({code: null}) survives a save and load round-trip', async () => {
  const storage = fakeStorage();
  await new SettingsStore(storage).save({ language: { code: null, name: '  Татарский ' } });
  assert.deepEqual((await new SettingsStore(storage).load()).language, { code: null, name: 'Татарский' });
});
