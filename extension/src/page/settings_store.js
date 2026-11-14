import { LANGUAGE_CHOICES } from '../shared/language_choices.js';
import { sanitizeLanguageName } from '../shared/translation_batch.js';

const SETTINGS_STORAGE_KEY = 'settings';
const MIN_TEXT_SCALE = 0.6;
const MAX_TEXT_SCALE = 2.0;
const MAX_CUSTOM_LANGUAGE_NAMES = 5;
const DEFAULT_BACKGROUND_OPACITY = 0.75;

export const TEXT_COLORS = Object.freeze(['white', 'yellow', 'cyan']);

/**
 * @typedef {{enabled: boolean, language: import('../shared/language_choices.js').TargetLanguage,
 *   customLanguageNames: string[], textScale: number, overlayPosition: {centerXFraction: number, bottomYFraction: number}|null,
 *   waitForSubtitles: boolean, textColor: 'white'|'yellow'|'cyan', backgroundOpacity: number, outline: boolean,
 *   hintSeen: boolean}} Settings
 */

/** @type {Settings} */
export const DEFAULT_SETTINGS = Object.freeze({
  enabled: false,
  language: Object.freeze({ code: 'ru', name: 'Russian' }),
  customLanguageNames: Object.freeze([]),
  textScale: 1,
  overlayPosition: null,
  waitForSubtitles: true,
  textColor: 'white',
  backgroundOpacity: DEFAULT_BACKGROUND_OPACITY,
  outline: false,
  hintSeen: false,
});

function isPlainObject(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function normalizeLanguage(value) {
  if (!isPlainObject(value)) return { ...DEFAULT_SETTINGS.language };
  const choice = LANGUAGE_CHOICES.find((candidate) => candidate.code === value.code);
  if (choice) return { code: choice.code, name: choice.englishName };
  if (value.code !== null || typeof value.name !== 'string') return { ...DEFAULT_SETTINGS.language };
  const name = sanitizeLanguageName(value.name);
  return name ? { code: null, name } : { ...DEFAULT_SETTINGS.language };
}

/** Sanitizes names, drops empty ones and case-insensitive duplicates (the first wins), keeps five. */
function normalizeCustomLanguageNames(value) {
  if (!Array.isArray(value)) return [];
  const seen = new Set();
  const names = [];
  for (const item of value) {
    if (typeof item !== 'string') continue;
    const name = sanitizeLanguageName(item);
    const identity = name.toLowerCase();
    if (!name || seen.has(identity)) continue;
    seen.add(identity);
    names.push(name);
  }
  return names.slice(0, MAX_CUSTOM_LANGUAGE_NAMES);
}

function normalizeTextScale(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return DEFAULT_SETTINGS.textScale;
  return Math.min(MAX_TEXT_SCALE, Math.max(MIN_TEXT_SCALE, value));
}

function normalizeTextColor(value) {
  return TEXT_COLORS.includes(value) ? value : DEFAULT_SETTINGS.textColor;
}

/** A non-number (a string too) is not a usable opacity: the default applies, not a clamped value. */
function normalizeBackgroundOpacity(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return DEFAULT_BACKGROUND_OPACITY;
  return Math.min(1, Math.max(0, value));
}

function isFractionOfPlayer(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
}

function normalizeOverlayPosition(value) {
  if (!isPlainObject(value)) return null;
  const { centerXFraction, bottomYFraction } = value;
  if (!isFractionOfPlayer(centerXFraction) || !isFractionOfPlayer(bottomYFraction)) return null;
  return { centerXFraction, bottomYFraction };
}

/** @returns {Settings} every field valid, missing or invalid ones taken from the defaults */
function normalizeSettings(raw) {
  const source = isPlainObject(raw) ? raw : {};
  return {
    enabled: typeof source.enabled === 'boolean' ? source.enabled : DEFAULT_SETTINGS.enabled,
    language: normalizeLanguage(source.language),
    customLanguageNames: normalizeCustomLanguageNames(source.customLanguageNames),
    textScale: normalizeTextScale(source.textScale),
    overlayPosition: normalizeOverlayPosition(source.overlayPosition),
    waitForSubtitles: typeof source.waitForSubtitles === 'boolean' ? source.waitForSubtitles : DEFAULT_SETTINGS.waitForSubtitles,
    textColor: normalizeTextColor(source.textColor),
    backgroundOpacity: normalizeBackgroundOpacity(source.backgroundOpacity),
    outline: typeof source.outline === 'boolean' ? source.outline : DEFAULT_SETTINGS.outline,
    hintSeen: typeof source.hintSeen === 'boolean' ? source.hintSeen : DEFAULT_SETTINGS.hintSeen,
  };
}

/** @returns {Settings} a fresh, mutable copy of the defaults */
function copyOfDefaultSettings() {
  return normalizeSettings({});
}

/**
 * Loads the settings at page start. The storage host runs in another content script that may
 * start later, so a rejected load (bridge timeout) is retried after a pause; when every attempt
 * fails the defaults are used. Never rejects.
 * @param {{load: () => Promise<Settings>}} settingsStore
 * @param {{sleep: (ms: number) => Promise<void>, attempts?: number, pauseMs?: number}} options
 * @returns {Promise<Settings>}
 */
export async function loadSettingsWithRetries(settingsStore, { sleep, attempts = 3, pauseMs = 1000 }) {
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await settingsStore.load();
    } catch {
      if (attempt < attempts) await sleep(pauseMs);
    }
  }
  return copyOfDefaultSettings();
}

/** Display settings kept in the extension storage; holds no tokens or account data. */
export class SettingsStore {
  /** @param {{get: Function, set: Function}} extensionStorage */
  constructor(extensionStorage) {
    this.extensionStorage = extensionStorage;
  }

  /** @returns {Promise<Settings>} */
  async load() {
    const stored = await this.extensionStorage.get([SETTINGS_STORAGE_KEY]);
    return normalizeSettings(stored[SETTINGS_STORAGE_KEY]);
  }

  /**
   * @param {Partial<Settings>} changes
   * @returns {Promise<Settings>} the settings as stored
   */
  async save(changes) {
    return this.update(() => changes);
  }

  /**
   * Loads the stored settings, merges the changes computed from them, and stores the result.
   * @param {(stored: Settings) => Partial<Settings>} computeChanges
   * @returns {Promise<Settings>} the settings as stored
   */
  async update(computeChanges) {
    const stored = await this.load();
    const merged = normalizeSettings({ ...stored, ...computeChanges(stored) });
    await this.extensionStorage.set({ [SETTINGS_STORAGE_KEY]: merged });
    return merged;
  }
}

/**
 * Saves setting changes from the page one after another. Only the changed fields are written,
 * merged into the settings loaded from storage right before the write, so a change made in
 * another tab (or values stored while this page used the defaults) is never overwritten.
 * A change may be a function of the freshly loaded settings (for lists such as the remembered
 * languages). Never rejects: a failed save resolves null and the next one still runs.
 * @param {SettingsStore} settingsStore
 * @returns {(changes: Partial<Settings>|((stored: Settings) => Partial<Settings>)) => Promise<Settings|null>}
 */
export function createSettingsSaver(settingsStore) {
  let previousSave = Promise.resolve();
  return (changes) => {
    const computeChanges = typeof changes === 'function' ? changes : () => changes;
    const result = previousSave.then(() => settingsStore.update(computeChanges)).catch(() => null);
    previousSave = result;
    return result;
  };
}
