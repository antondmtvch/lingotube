/** A word is never shown as lasting longer than this before a pause. */
export const MAX_WORD_DURATION_MS = 1500;

/**
 * @typedef {{text: string, startMs: number, endMs: number}} TimedWord
 */

/**
 * Turns a YouTube json3 caption document into timed words.
 * Automatic captions carry per-word offsets (`tOffsetMs`); manual captions
 * carry one whole line per event, which becomes a single TimedWord.
 * @param {object} json3
 * @returns {TimedWord[]}
 */
export function timedWordsFromJson3(json3) {
  const events = Array.isArray(json3?.events) ? json3.events : [];
  const eventsWithText = events.filter(
    (event) => Array.isArray(event?.segs) && Number.isFinite(event.tStartMs),
  );
  const hasWordOffsets = eventsWithText.some((event) =>
    event.segs.some((seg) => typeof seg?.tOffsetMs === 'number'),
  );
  return hasWordOffsets ? wordsFromOffsets(eventsWithText) : wordsFromLines(eventsWithText);
}

function wordsFromOffsets(events) {
  const words = [];
  for (const event of events) {
    for (const seg of event.segs) {
      const text = typeof seg?.utf8 === 'string' ? seg.utf8.trim() : '';
      if (!text) continue;
      words.push({ text, startMs: event.tStartMs + (seg.tOffsetMs ?? 0), endMs: 0 });
    }
  }
  words.forEach((word, index) => {
    const nextStartMs = words[index + 1]?.startMs ?? Infinity;
    word.endMs = Math.min(nextStartMs, word.startMs + MAX_WORD_DURATION_MS);
  });
  return words;
}

function wordsFromLines(events) {
  const words = [];
  for (const event of events) {
    const text = event.segs
      .map((seg) => (typeof seg?.utf8 === 'string' ? seg.utf8 : ''))
      .join('')
      .replace(/\s+/g, ' ')
      .trim();
    if (!text) continue;
    words.push({ text, startMs: event.tStartMs, endMs: event.tStartMs + (event.dDurationMs ?? 0) });
  }
  return words;
}
