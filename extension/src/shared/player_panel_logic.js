import { sanitizeLanguageName } from './translation_batch.js';

export const TEXT_SCALE_STEP = 0.2;
export const MIN_TEXT_SCALE = 0.6;
export const MAX_TEXT_SCALE = 2.0;
const CUSTOM_VALUE_PREFIX = 'custom:';

/**
 * Turns the text typed into the "other language" input into a target language.
 * @param {string} typedText
 * @returns {import('./language_choices.js').TargetLanguage|null} null for empty or whitespace-only text
 */
export function languageFromTypedText(typedText) {
  const name = sanitizeLanguageName(String(typedText ?? ''));
  return name ? { code: null, name } : null;
}

/**
 * The dropdown value that stands for the given language (the inverse of targetLanguageFromMenuValue).
 * @param {import('./language_choices.js').TargetLanguage} language
 * @returns {string}
 */
export function menuValueForLanguage(language) {
  return language.code === null ? `${CUSTOM_VALUE_PREFIX}${language.name}` : language.code;
}

/**
 * Typed language names for the dropdown: the remembered ones, plus the current language
 * when it is typed and not remembered yet, so the select can always show it.
 * @param {string[]} customLanguageNames
 * @param {import('./language_choices.js').TargetLanguage} currentLanguage
 * @returns {string[]}
 */
export function customNamesForMenu(customLanguageNames, currentLanguage) {
  if (currentLanguage.code !== null) return [...customLanguageNames];
  const currentIdentity = currentLanguage.name.toLowerCase();
  const isRemembered = customLanguageNames.some((name) => name.toLowerCase() === currentIdentity);
  return isRemembered ? [...customLanguageNames] : [currentLanguage.name, ...customLanguageNames];
}

/**
 * @param {number} currentScale
 * @param {1|-1} direction 1 to enlarge, -1 to shrink
 * @returns {number} the scale one step away, kept within the allowed range
 */
export function steppedTextScale(currentScale, direction) {
  const stepped = Math.round((currentScale + direction * TEXT_SCALE_STEP) * 100) / 100;
  return Math.min(MAX_TEXT_SCALE, Math.max(MIN_TEXT_SCALE, stepped));
}

/**
 * The dropdown value to show once the "other language" input is abandoned or confirmed:
 * always the value of the language that is actually in use, never the "other" item.
 * @param {import('./language_choices.js').TargetLanguage} currentLanguage
 * @returns {string}
 */
export function selectValueAfterClose(currentLanguage) {
  return menuValueForLanguage(currentLanguage);
}

/**
 * Puts the button right before the subtitles button, in whatever element holds it
 * (it may be nested inside a wrapper); without that button, first among the right controls.
 * @param {{rightControls: object, subtitlesButton: object|null, button: object}} elements
 */
export function placeButtonNextToSubtitlesButton({ rightControls, subtitlesButton, button }) {
  if (subtitlesButton && subtitlesButton.parentNode) {
    subtitlesButton.parentNode.insertBefore(button, subtitlesButton);
    return;
  }
  rightControls.insertBefore(button, rightControls.firstChild);
}
