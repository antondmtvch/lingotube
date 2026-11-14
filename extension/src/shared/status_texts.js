// User-facing status texts of the overlay.
import { uiTexts } from './ui_strings.js';

const STATUS_KEYS = [
  'translating',
  'translationDelayed',
  'approximateTiming',
  'captionsNotFetched',
  'chatUnavailable',
  'notSignedIn',
  'repeatedFailures',
  'noSpeech',
];

/**
 * @param {string} languageCode an interface language code (see UI_LANGUAGES)
 * @returns {Record<string, string>} the status texts of that language
 */
export function statusTextsFor(languageCode) {
  const texts = uiTexts(languageCode);
  return Object.fromEntries(STATUS_KEYS.map((key) => [key, texts[key]]));
}

/** The Russian statuses; the default of the overlay and what the tests expect. */
export const STATUS_TEXTS = statusTextsFor('ru');

/** @param {number} minutesLeft whole minutes until requests may resume */
export function rateLimitedText(minutesLeft) {
  return uiTexts('ru').rateLimited(minutesLeft);
}
