import { fillPrompt } from './prompt_texts.js';

/** @typedef {import('./sentence_cues.js').Cue} Cue */

const MAX_LANGUAGE_NAME_LENGTH = 60;
const REPLY_LINE_PATTERN = /^\s*(\d+)(?:[\t ]+|[.):]\s*)(.*?)\s*$/;

/**
 * Turns the language typed by the person into one short line.
 * @param {string} text
 * @returns {string}
 */
export function sanitizeLanguageName(text) {
  return text.split(/\s+/).filter(Boolean).join(' ').slice(0, MAX_LANGUAGE_NAME_LENGTH).trim();
}

/**
 * Builds the chat message: the batch prompt, then one "<id>\t<text>" line per cue.
 * @param {string} languageName
 * @param {Cue[]} cues
 * @returns {string}
 */
export function buildTranslationPrompt(languageName, cues) {
  const head = fillPrompt('translate_batch', { language: sanitizeLanguageName(languageName) });
  const lines = cues.map((cue) => `${cue.id}\t${cue.sourceText.split(/\s+/).filter(Boolean).join(' ')}`);
  return `${head}\n${lines.join('\n')}`;
}

/**
 * Matches reply lines to cues by id only. A reply whose ids are out of the expected
 * order or repeat is rejected whole; ids that were not asked for are skipped.
 * @param {string} answer
 * @param {number[]} expectedCueIds
 * @returns {{translationsByCueId: Map<number, string>, missingCueIds: number[]}}
 */
export function parseTranslationReply(answer, expectedCueIds) {
  const positionByCueId = new Map(expectedCueIds.map((id, position) => [id, position]));
  const translationsByCueId = new Map();
  let lastPosition = -1;
  for (const line of answer.split(/\r?\n/)) {
    const match = REPLY_LINE_PATTERN.exec(line);
    if (!match) continue;
    const id = Number(match[1]);
    const text = match[2];
    const position = positionByCueId.get(id);
    if (position === undefined || text === '') continue;
    if (translationsByCueId.has(id) || position < lastPosition) {
      return { translationsByCueId: new Map(), missingCueIds: [...expectedCueIds] };
    }
    lastPosition = position;
    translationsByCueId.set(id, text);
  }
  return {
    translationsByCueId,
    missingCueIds: expectedCueIds.filter((id) => !translationsByCueId.has(id)),
  };
}
