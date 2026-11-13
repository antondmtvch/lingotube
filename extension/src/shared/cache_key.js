import { PROMPT_VERSION } from './prompt_texts.js';
import { CUE_RULES_VERSION } from './sentence_cues.js';
import { CUSTOM_LANGUAGE_CODE } from './language_choices.js';

/** Source key of cues taken from the chat transcript instead of a caption track. */
export const CHAT_TRANSCRIPT_SOURCE_KEY = 'chat';

/**
 * The code of a listed language, or "custom:" plus the typed name, trimmed and lower-cased.
 * @param {import('./language_choices.js').TargetLanguage} language
 * @returns {string}
 */
export function languageCacheKey(language) {
  if (language.code === CUSTOM_LANGUAGE_CODE) return `custom:${language.name.trim().toLowerCase()}`;
  return language.code;
}

/**
 * @param {import('./caption_track_choice.js').CaptionTrackInfo} track
 * @returns {string}
 */
export function captionSourceKey(track) {
  return `${track.languageCode}.${track.kind}`;
}

/**
 * Storage key of one cached translation; holds no account data.
 * @param {{videoId: string, language: import('./language_choices.js').TargetLanguage, sourceKey: string}} parts
 * @returns {string}
 */
export function translationCacheKey({ videoId, language, sourceKey }) {
  return `cache:${videoId}|${languageCacheKey(language)}|${sourceKey}|p${PROMPT_VERSION}|c${CUE_RULES_VERSION}`;
}
