/** @typedef {import('./timestamped_transcript.js').TimedLine} TimedLine */

/** Length of one transcript request: longer chunks were seen cut off by the chat. */
export const CHUNK_MS = 300000;
/** The next chunk is requested when less than this remains in the current one. */
export const TRANSCRIPT_RESERVE_AHEAD_MS = 120000;

/**
 * @param {number} index
 * @param {number} durationMs
 * @returns {{startMs: number, endMs: number}} the last chunk ends with the video
 */
export function chunkBounds(index, durationMs) {
  return { startMs: index * CHUNK_MS, endMs: Math.min((index + 1) * CHUNK_MS, durationMs) };
}

/**
 * Lines of one chunk answer placed on the video timeline. The chat answers with video times
 * (as the CLI sees them); if every line starts before the chunk, it counted from the chunk
 * start instead, and the chunk start is added. Lines outside the chunk are dropped: cues
 * never move from one chunk to another.
 * @template {{startMs: number, endMs: number|null, text: string}} Line
 * @param {Line[]} lines
 * @param {{startMs: number, endMs: number}} bounds
 * @returns {Line[]}
 */
export function linesInsideChunk(lines, { startMs, endMs }) {
  const isChunkRelative = startMs > 0 && lines.length > 0 && lines.every((line) => line.startMs < startMs);
  const offsetMs = isChunkRelative ? startMs : 0;
  return lines
    .map((line) => ({
      ...line,
      startMs: line.startMs + offsetMs,
      endMs: line.endMs === null ? null : line.endMs + offsetMs,
    }))
    .filter((line) => line.startMs >= startMs && line.startMs < endMs);
}

function isPlainObject(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isWellFormedLine(line) {
  return isPlainObject(line) && Number.isFinite(line.startMs) && Number.isFinite(line.endMs)
    && typeof line.text === 'string';
}

/**
 * The chat transcript of one video, in chunks of CHUNK_MS. A chunk is missing, loaded (its
 * cues) or failed (the chat gave no lines for it).
 */
export class TranscriptChunkStore {
  #durationMs;
  #chunkCount;
  /** @type {Map<number, TimedLine[]>} */
  #cuesByChunkIndex = new Map();
  #failedChunkIndexes = new Set();

  /** @param {number} durationMs */
  constructor(durationMs) {
    this.#durationMs = Math.max(0, Number(durationMs) || 0);
    this.#chunkCount = Math.ceil(this.#durationMs / CHUNK_MS);
  }

  get durationMs() {
    return this.#durationMs;
  }

  get chunkCount() {
    return this.#chunkCount;
  }

  /** @returns {number} index of the chunk holding timeMs (may be past the last chunk) */
  chunkIndexAt(timeMs) {
    return Math.floor(Math.max(0, timeMs) / CHUNK_MS);
  }

  hasChunk(index) {
    return this.#cuesByChunkIndex.has(index);
  }

  isChunkFailed(index) {
    return this.#failedChunkIndexes.has(index);
  }

  /**
   * Stores the cues of a chunk, clamped to its bounds: cues starting outside it are dropped,
   * ends past it are cut.
   * @param {number} index
   * @param {TimedLine[]} cues
   */
  addChunk(index, cues) {
    if (!this.#isChunkIndex(index)) return;
    const { startMs, endMs } = chunkBounds(index, this.#durationMs);
    const kept = cues
      .filter((cue) => cue.startMs >= startMs && cue.startMs < endMs)
      .map((cue) => ({ startMs: cue.startMs, endMs: Math.min(cue.endMs, endMs), text: cue.text }))
      .sort((first, second) => first.startMs - second.startMs);
    this.#cuesByChunkIndex.set(index, kept);
    this.#failedChunkIndexes.delete(index);
  }

  markChunkFailed(index) {
    if (this.#isChunkIndex(index) && !this.hasChunk(index)) this.#failedChunkIndexes.add(index);
  }

  /** Turns every failed chunk back into missing (the "retry" action). */
  resetFailed() {
    this.#failedChunkIndexes.clear();
  }

  /** @returns {boolean} true when the video has chunks and every one of them failed */
  areAllChunksFailed() {
    return this.#chunkCount > 0 && this.#failedChunkIndexes.size === this.#chunkCount;
  }

  /** @returns {number} chunks with cues */
  get loadedChunkCount() {
    return this.#cuesByChunkIndex.size;
  }

  /** @returns {{kind:'nothing'}|{kind:'text',text:string}|{kind:'waiting'}|{kind:'failed'}} */
  displayAt(timeMs) {
    if (timeMs < 0 || timeMs >= this.#durationMs) return { kind: 'nothing' };
    const index = this.chunkIndexAt(timeMs);
    const cues = this.#cuesByChunkIndex.get(index);
    if (cues) {
      const cue = cues.find((candidate) => candidate.startMs <= timeMs && timeMs < candidate.endMs);
      return cue ? { kind: 'text', text: cue.text } : { kind: 'nothing' };
    }
    if (this.isChunkFailed(index)) return { kind: 'failed' };
    return { kind: 'waiting' };
  }

  /**
   * The chunk under the playhead when it is missing; else the next one when less than
   * `reserveAheadMs` remain in the current chunk and the next one is missing; else null
   * (past the end, or the chunk is loaded or failed).
   * @returns {number|null}
   */
  nextChunkToRequest(positionMs, reserveAheadMs = TRANSCRIPT_RESERVE_AHEAD_MS) {
    const index = this.chunkIndexAt(positionMs);
    if (index >= this.#chunkCount) return null;
    if (this.#isChunkMissing(index)) return index;
    const nextIndex = index + 1;
    if (nextIndex >= this.#chunkCount) return null;
    const remainingMs = chunkBounds(index, this.#durationMs).endMs - positionMs;
    if (remainingMs < reserveAheadMs && this.#isChunkMissing(nextIndex)) return nextIndex;
    return null;
  }

  /** @returns {{chunks: Object<string, TimedLine[]>}} the loaded chunks, for the cache */
  toCacheEntry() {
    const chunks = {};
    for (const [index, cues] of [...this.#cuesByChunkIndex].sort(([first], [second]) => first - second)) {
      chunks[index] = cues.map(({ startMs, endMs, text }) => ({ startMs, endMs, text }));
    }
    return { chunks };
  }

  /**
   * Loads the well-formed chunks of a cache entry; malformed ones, empty ones and those
   * outside the video are skipped.
   * @param {unknown} entry
   * @returns {number} chunks loaded
   */
  loadCacheEntry(entry) {
    if (!isPlainObject(entry) || !isPlainObject(entry.chunks)) return 0;
    let loadedCount = 0;
    for (const [key, cues] of Object.entries(entry.chunks)) {
      if (!/^\d+$/.test(key)) continue;
      const index = Number(key);
      if (!this.#isChunkIndex(index)) continue;
      if (!Array.isArray(cues) || cues.length === 0 || !cues.every(isWellFormedLine)) continue;
      this.addChunk(index, cues);
      loadedCount += 1;
    }
    return loadedCount;
  }

  #isChunkIndex(index) {
    return Number.isInteger(index) && index >= 0 && index < this.#chunkCount;
  }

  #isChunkMissing(index) {
    return !this.hasChunk(index) && !this.isChunkFailed(index);
  }
}
