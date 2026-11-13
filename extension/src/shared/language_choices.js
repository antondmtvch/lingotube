import { sanitizeLanguageName } from './translation_batch.js';

/**
 * @typedef {{code: string, name: string}} TargetLanguage
 * A listed language has its list code and English name; a typed one has code 'custom'.
 */

export const CUSTOM_LANGUAGE_CODE = 'custom';
export const OTHER_LANGUAGE_VALUE = '__other__';
const CUSTOM_VALUE_PREFIX = 'custom:';
const FALLBACK_PROMPT_LANGUAGE = 'Russian';

/** The 30 languages of the dropdown, in the order of the spec; each is labeled in its own language. */
export const LANGUAGE_CHOICES = [
  { code: 'en', nativeName: 'English', englishName: 'English' },
  { code: 'zh-Hans', nativeName: '简体中文', englishName: 'Chinese (Simplified)' },
  { code: 'zh-Hant', nativeName: '繁體中文', englishName: 'Chinese (Traditional)' },
  { code: 'hi', nativeName: 'हिन्दी', englishName: 'Hindi' },
  { code: 'es', nativeName: 'Español', englishName: 'Spanish' },
  { code: 'fr', nativeName: 'Français', englishName: 'French' },
  { code: 'ar', nativeName: 'العربية', englishName: 'Arabic' },
  { code: 'bn', nativeName: 'বাংলা', englishName: 'Bengali' },
  { code: 'pt', nativeName: 'Português', englishName: 'Portuguese' },
  { code: 'ru', nativeName: 'Русский', englishName: 'Russian' },
  { code: 'ur', nativeName: 'اردو', englishName: 'Urdu' },
  { code: 'id', nativeName: 'Bahasa Indonesia', englishName: 'Indonesian' },
  { code: 'de', nativeName: 'Deutsch', englishName: 'German' },
  { code: 'ja', nativeName: '日本語', englishName: 'Japanese' },
  { code: 'tr', nativeName: 'Türkçe', englishName: 'Turkish' },
  { code: 'ko', nativeName: '한국어', englishName: 'Korean' },
  { code: 'vi', nativeName: 'Tiếng Việt', englishName: 'Vietnamese' },
  { code: 'it', nativeName: 'Italiano', englishName: 'Italian' },
  { code: 'th', nativeName: 'ไทย', englishName: 'Thai' },
  { code: 'pl', nativeName: 'Polski', englishName: 'Polish' },
  { code: 'uk', nativeName: 'Українська', englishName: 'Ukrainian' },
  { code: 'nl', nativeName: 'Nederlands', englishName: 'Dutch' },
  { code: 'fa', nativeName: 'فارسی', englishName: 'Persian' },
  { code: 'he', nativeName: 'עברית', englishName: 'Hebrew' },
  { code: 'el', nativeName: 'Ελληνικά', englishName: 'Greek' },
  { code: 'cs', nativeName: 'Čeština', englishName: 'Czech' },
  { code: 'sv', nativeName: 'Svenska', englishName: 'Swedish' },
  { code: 'ro', nativeName: 'Română', englishName: 'Romanian' },
  { code: 'hu', nativeName: 'Magyar', englishName: 'Hungarian' },
  { code: 'kk', nativeName: 'Қазақша', englishName: 'Kazakh' },
];

/**
 * Items of the language dropdown: typed names first, then the listed languages, then "other".
 * @param {string[]} customLanguageNames
 * @returns {{value: string, label: string}[]}
 */
export function buildLanguageMenu(customLanguageNames) {
  return [
    ...customLanguageNames.map((name) => ({ value: `${CUSTOM_VALUE_PREFIX}${name}`, label: name })),
    ...LANGUAGE_CHOICES.map((choice) => ({ value: choice.code, label: choice.nativeName })),
    { value: OTHER_LANGUAGE_VALUE, label: 'Другой язык…' },
  ];
}

/**
 * @param {string} value a value of the menu built by buildLanguageMenu
 * @returns {TargetLanguage|null} null for "other", unknown values and empty typed names
 */
export function targetLanguageFromMenuValue(value) {
  if (value.startsWith(CUSTOM_VALUE_PREFIX)) {
    const name = sanitizeLanguageName(value.slice(CUSTOM_VALUE_PREFIX.length));
    return name ? { code: CUSTOM_LANGUAGE_CODE, name } : null;
  }
  const choice = LANGUAGE_CHOICES.find((candidate) => candidate.code === value);
  return choice ? { code: choice.code, name: choice.englishName } : null;
}

/**
 * The language name that goes into the prompt; never empty.
 * @param {TargetLanguage} language
 * @returns {string}
 */
export function promptLanguageName(language) {
  const choice = LANGUAGE_CHOICES.find((candidate) => candidate.code === language.code);
  if (choice) return choice.englishName;
  return sanitizeLanguageName(String(language.name ?? '')) || FALLBACK_PROMPT_LANGUAGE;
}
