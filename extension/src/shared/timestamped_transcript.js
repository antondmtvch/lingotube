// Port of the chat answer format of src/lingotube/prompts/FORMAT.md: `parse_answer`
// (src/lingotube/parsing.py), `keep_second_of_identical` (features/transcript.py) and
// `fix_ends` (assemble.py).

/** @typedef {{startMs: number, endMs: number|null, text: string}} TimestampedLine */
/** @typedef {{startMs: number, endMs: number, text: string}} TimedLine */

const TIME_PATTERN = String.raw`\d{1,3}:\d{2}(?::\d{2})?`;
// The Python pattern uses possessive quantifiers; JavaScript has none, so the runs of spaces
// and asterisks are matched atomically with the (?=(x))\k<x> idiom. Without it a long run of
// spaces makes the overlapping \s+ / \s* backtrack quadratically.
const TIMESTAMPED_LINE_PATTERN = new RegExp(
  String.raw`^(?:(?:[-*•–—]|\d{1,3}[.)])(?=(?<listSpace>\s+))\k<listSpace>)?`
  + String.raw`(?=(?<bold>\**))\k<bold>(?=(?<boldSpace>\s*))\k<boldSpace>[(\[]\s*`
  + `(?<start>${TIME_PATTERN})(?:\\s*[-–—]\\s*(?<end>${TIME_PATTERN}))?`
  + String.raw`\s*[)\]]\s*\**\s*(?<text>.*)$`,
  'u',
);
// The line breaks of Python's str.splitlines().
const LINE_BREAK_PATTERN = /\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/;

const READING_MIN_MS = 1500;
const READING_MAX_MS = 7000;
const READING_CHARACTERS_PER_SECOND = 15;

/** Milliseconds of `m:ss` / `h:mm:ss`; null when a part is out of range (0-59, hours 0-99). */
function timestampMs(stamp) {
  const parts = stamp.split(':').map(Number);
  if (parts.slice(1).some((part) => part > 59) || (parts.length === 3 && parts[0] > 99)) return null;
  return parts.reduce((total, part) => total * 60 + part, 0) * 1000;
}

/**
 * Of two consecutive lines with the same start and end only the second is kept: the chat
 * sometimes gives the original and then the translation under one timestamp.
 * @param {TimestampedLine[]} lines
 * @returns {TimestampedLine[]}
 */
function keepSecondOfIdentical(lines) {
  const kept = [];
  for (let index = 0; index < lines.length; index += 1) {
    const next = lines[index + 1];
    if (next && next.startMs === lines[index].startMs && next.endMs === lines[index].endMs) {
      kept.push(next);
      index += 1;
    } else {
      kept.push(lines[index]);
    }
  }
  return kept;
}

/**
 * Lines of a chat answer in the `(m:ss) text` format; [] when it has no timestamps. Never throws.
 * Intro before the first timestamp and outro after a blank line are dropped; a line without a
 * timestamp joins the previous one.
 * @param {string} text
 * @returns {TimestampedLine[]}
 */
export function parseTimestampedAnswer(text) {
  const lines = [];
  let isAfterBlankLine = false;
  for (const rawLine of String(text).split(LINE_BREAK_PATTERN)) {
    const line = rawLine.trim();
    const match = TIMESTAMPED_LINE_PATTERN.exec(line);
    if (match) {
      const { bold, start, end, text: body } = match.groups;
      const startMs = timestampMs(start);
      let endMs = end ? timestampMs(end) : null;
      if (startMs !== null && (endMs !== null || !end)) {
        if (endMs !== null && endMs < startMs) endMs = null; // the reading time decides the end
        let lineText = body.trim();
        if (bold) lineText = lineText.replace(/\*+$/, '').trim(); // "**(0:02) x**": closing bold
        lines.push({ startMs, endMs, text: lineText });
        isAfterBlankLine = false;
        continue;
      }
    }
    if (lines.length === 0) continue; // intro before the first timestamp
    if (!line) isAfterBlankLine = true;
    else if (!isAfterBlankLine) lines.at(-1).text = `${lines.at(-1).text} ${line}`.trim();
    // else: outro after a blank line, dropped
  }
  return keepSecondOfIdentical(lines.filter((parsed) => parsed.text));
}

/**
 * Gives every line an end: the chat's own end when it is after the start, else the reading
 * time (1.5-7 s at 15 characters per second); never past the next later start or `chunkEndMs`.
 * Lines starting at or after `chunkEndMs` are dropped.
 * @param {TimestampedLine[]} lines sorted by start
 * @param {number} chunkEndMs
 * @returns {TimedLine[]}
 */
export function withReadingTimeEnds(lines, chunkEndMs) {
  const kept = lines.filter((line) => line.startMs < chunkEndMs);
  return kept.map((line, index) => {
    const nextStart = kept.slice(index + 1).find((later) => later.startMs > line.startMs)?.startMs;
    const limitMs = nextStart === undefined ? chunkEndMs : Math.min(chunkEndMs, nextStart);
    let endMs;
    if (line.endMs !== null && line.endMs > line.startMs) {
      endMs = Math.min(line.endMs, limitMs);
    } else {
      const characters = [...line.text].length;
      const readingMs = Math.min(
        Math.max((characters / READING_CHARACTERS_PER_SECOND) * 1000, READING_MIN_MS),
        READING_MAX_MS,
      );
      endMs = Math.min(line.startMs + readingMs, limitMs);
    }
    return { startMs: line.startMs, endMs, text: line.text };
  });
}

/**
 * Time for the transcript prompt: `m:ss` below one hour, `h:mm:ss` from one hour.
 * @param {number} ms
 * @param {{roundUp?: boolean}} [options] roundUp: whole seconds rounded up (for a range end)
 * @returns {string}
 */
export function formatPromptTime(ms, { roundUp = false } = {}) {
  const seconds = ms / 1000;
  const total = Math.max(roundUp ? Math.ceil(seconds) : Math.floor(seconds), 0);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secondsPart = String(total % 60).padStart(2, '0');
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, '0')}:${secondsPart}`;
  return `${minutes}:${secondsPart}`;
}
