import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_SETTINGS, SettingsStore, createSettingsSaver, loadSettingsWithRetries } from '../src/page/settings_store.js';

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
    waitForSubtitles: true,
  });
});

test('settings: waitForSubtitles defaults to true', async () => {
  assert.equal(DEFAULT_SETTINGS.waitForSubtitles, true);
  assert.equal((await new SettingsStore(fakeStorage()).load()).waitForSubtitles, true);
});

test('settings: waitForSubtitles keeps a stored boolean and replaces a non-boolean with true', async () => {
  const load = (stored) => new SettingsStore(fakeStorage({ settings: stored })).load();
  assert.equal((await load({ waitForSubtitles: false })).waitForSubtitles, false);
  assert.equal((await load({ waitForSubtitles: 'no' })).waitForSubtitles, true);
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

// --- Loading at page start, when the storage host may answer late (Task 12). ---

/** A settings store whose first `failures` loads reject, as a late storage bridge would. */
function lateSettingsStore(failures, settings) {
  let calls = 0;
  return {
    get calls() {
      return calls;
    },
    async load() {
      calls += 1;
      if (calls <= failures) throw new Error('extension storage did not answer');
      return settings;
    },
  };
}

test('settings retry: two rejected loads, then the stored settings are used', async () => {
  const stored = { ...DEFAULT_SETTINGS, enabled: true };
  const store = lateSettingsStore(2, stored);
  const pauses = [];
  const settings = await loadSettingsWithRetries(store, { sleep: async (ms) => pauses.push(ms) });
  assert.equal(settings, stored);
  assert.equal(store.calls, 3);
  assert.deepEqual(pauses, [1000, 1000]);
});

test('settings retry: a store that keeps rejecting gives fresh defaults after three attempts', async () => {
  const store = lateSettingsStore(Infinity, null);
  const settings = await loadSettingsWithRetries(store, { sleep: async () => {} });
  assert.equal(store.calls, 3);
  assert.deepEqual(settings, DEFAULT_SETTINGS);
  assert.ok(!Object.isFrozen(settings) && !Object.isFrozen(settings.language));
});

// --- Saving changes from the page (Task 12 fix): only the changed fields, merged into fresh stored values. ---

test('settings saver: saving {overlayPosition} keeps an enabled and a language changed in between', async () => {
  const storage = fakeStorage();
  const saveSettingsChange = createSettingsSaver(new SettingsStore(storage));
  await saveSettingsChange({ enabled: true });
  // Another tab changes the language after this page loaded its settings.
  storage.data.set('settings', { ...storage.data.get('settings'), language: { code: 'en', name: 'English' } });
  await saveSettingsChange({ overlayPosition: { centerXFraction: 0.3, bottomYFraction: 0.7 } });
  const stored = await new SettingsStore(storage).load();
  assert.equal(stored.enabled, true);
  assert.deepEqual(stored.language, { code: 'en', name: 'English' });
  assert.deepEqual(stored.overlayPosition, { centerXFraction: 0.3, bottomYFraction: 0.7 });
});

test('settings saver: a change computed from the stored settings sees the fresh stored values', async () => {
  const storage = fakeStorage({ settings: { customLanguageNames: ['Klingon'] } });
  const saveSettingsChange = createSettingsSaver(new SettingsStore(storage));
  const seen = [];
  await saveSettingsChange((stored) => {
    seen.push(stored.customLanguageNames);
    return { customLanguageNames: ['Elvish', ...stored.customLanguageNames] };
  });
  assert.deepEqual(seen, [['Klingon']]);
  assert.deepEqual((await new SettingsStore(storage).load()).customLanguageNames, ['Elvish', 'Klingon']);
});

test('settings saver: quick successive changes run one after another and a failure does not stop the queue', async () => {
  const storage = fakeStorage();
  let failNextSet = true;
  const originalSet = storage.set;
  storage.set = async (items) => {
    if (failNextSet) {
      failNextSet = false;
      throw new Error('extension storage did not answer');
    }
    return originalSet(items);
  };
  const saveSettingsChange = createSettingsSaver(new SettingsStore(storage));
  const results = await Promise.all([
    saveSettingsChange({ textScale: 1.2 }),
    saveSettingsChange({ enabled: true }),
    saveSettingsChange({ textScale: 1.4 }),
  ]);
  assert.equal(results[0], null);
  const stored = await new SettingsStore(storage).load();
  assert.equal(stored.enabled, true);
  assert.equal(stored.textScale, 1.4);
});
