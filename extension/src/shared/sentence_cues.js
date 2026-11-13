/** Bump when the cue-building rules change, so cached cues and translations are rebuilt. */
export const CUE_RULES_VERSION = '1';

/**
 * Starting values; they are tuned on real videos later.
 * `maxChars` and `maxDurationMs` limit one cue, `pauseMs` is the silence that ends a cue.
 */
export const DEFAULT_CUE_RULES = Object.freeze({
  maxChars: 84,
  maxDurationMs: 7000,
  pauseMs: 700,
});

/**
 * @typedef {{text: string, startMs: number, endMs: number}} TimedWord
 * @typedef {{id: number, startMs: number, endMs: number, sourceText: string}} Cue
 */

const SENTENCE_END_PATTERN = /[.!?…。！？]["'”’»)\]」』）]*$/;
const CLAUSE_END_PATTERN = /[,;:]["'”’»)\]」』）]*$/;

const endsSentence = (word) => SENTENCE_END_PATTERN.test(word.text);
const endsClause = (word) => CLAUSE_END_PATTERN.test(word.text);
const joinWords = (words) => words.map((word) => word.text).join(' ');

/**
 * Groups timed words into cues: whole sentences, or parts of long sentences,
 * split at pauses and commas so each cue fits the subtitle box and its own duration.
 * @param {TimedWord[]} words
 * @param {{maxChars: number, maxDurationMs: number, pauseMs: number}} rules
 * @returns {Cue[]}
 */
export function buildCues(words, rules = DEFAULT_CUE_RULES) {
  const wordGroups = [];
  let current = [];

  const closeCurrent = () => {
    if (current.length > 0) wordGroups.push(current);
    current = [];
  };

  const wouldOverflow = (nextWord) =>
    joinWords(current).length + 1 + nextWord.text.length > rules.maxChars ||
    nextWord.endMs - current[0].startMs > rules.maxDurationMs;

  words.forEach((word, index) => {
    while (current.length > 0 && wouldOverflow(word)) {
      const remainder = splitAtClauseEnd(current);
      closeCurrent();
      current = remainder;
    }
    current.push(word);

    const nextWord = words[index + 1];
    if (endsSentence(word) || (nextWord && nextWord.startMs - word.endMs >= rules.pauseMs)) {
      closeCurrent();
    }
  });
  closeCurrent();

  return wordGroups.map((group, index) => {
    const nextGroup = wordGroups[index + 1];
    const lastWordEndMs = group[group.length - 1].endMs;
    return {
      id: index + 1,
      startMs: group[0].startMs,
      endMs: nextGroup ? Math.min(lastWordEndMs, nextGroup[0].startMs) : lastWordEndMs,
      sourceText: joinWords(group),
    };
  });
}

/**
 * Pushes `groupWords` back to a closable state when a word overflows the cue:
 * if the last clause end lies past the midpoint of the text, the words after it
 * are returned as the remainder and `groupWords` is cut after it; otherwise
 * nothing is cut and the remainder is empty.
 * Mutates `groupWords` (truncates it) and returns the words that were cut off.
 */
function splitAtClauseEnd(groupWords) {
  const midpoint = joinWords(groupWords).length / 2;
  let lengthSoFar = 0;
  let cutAfterIndex = -1;
  groupWords.forEach((word, index) => {
    lengthSoFar += word.text.length + (index > 0 ? 1 : 0);
    if (endsClause(word) && lengthSoFar > midpoint) cutAfterIndex = index;
  });
  if (cutAfterIndex === -1) return [];
  return groupWords.splice(cutAfterIndex + 1);
}
