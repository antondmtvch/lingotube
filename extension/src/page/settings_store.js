import { LANGUAGE_CHOICES } from '../shared/language_choices.js';
import { sanitizeLanguageName } from '../shared/translation_batch.js';

const SETTINGS_STORAGE_KEY = 'settings';
const MIN_TEXT_SCALE = 0.6;
const MAX_TEXT_SCALE = 2.0;
const MAX_CUSTOM_LANGUAGE_NAMES = 5;

/**
 * @typedef {{enabled: boolean, language: import('../shared/language_choices.js').TargetLanguage,
 *   customLanguageNames: string[], textScale: number, overlayPosition: {centerXFraction: number, bottomYFraction: number}|null}} Settings
 */

/** @type {Settings} */
export const DEFAULT_SETTINGS = Object.freeze({
  enabled: false,
  language: Object.freeze({ code: 'ru', name: 'Russian' }),
  customLanguageNames: Object.freeze([]),
  textScale: 1,
  overlayPosition: null,
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
  };
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
    const merged = normalizeSettings({ ...(await this.load()), ...changes });
    await this.extensionStorage.set({ [SETTINGS_STORAGE_KEY]: merged });
    return merged;
  }
}
