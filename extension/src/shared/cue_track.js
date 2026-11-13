/** @typedef {{id: number, startMs: number, endMs: number, sourceText: string}} Cue */
/** @typedef {'none'|'pending'|'done'|'failed'} TranslationState */

/** The in-memory model of one video: its cues and the translation state of each. */
export class CueTrack {
  #cues;
  #stateByCueId = new Map();
  #translationTextByCueId = new Map();

  /** @param {Cue[]} cues cues sorted by startMs; gaps between them are allowed */
  constructor(cues) {
    this.#cues = cues;
    for (const cue of cues) this.#stateByCueId.set(cue.id, 'none');
  }

  /** @returns {readonly Cue[]} */
  get cues() {
    return this.#cues;
  }

  /** Index of the first cue whose endMs is greater than timeMs (cues.length when none). */
  #indexOfFirstCueEndingAfter(timeMs) {
    let low = 0;
    let high = this.#cues.length;
    while (low < high) {
      const middle = (low + high) >> 1;
      if (this.#cues[middle].endMs > timeMs) high = middle;
      else low = middle + 1;
    }
    return low;
  }

  /** @returns {Cue|null} the cue with startMs <= timeMs < endMs */
  cueAt(timeMs) {
    const cue = this.#cues[this.#indexOfFirstCueEndingAfter(timeMs)];
    return cue && cue.startMs <= timeMs ? cue : null;
  }

  /** @returns {TranslationState} */
  translationState(cueId) {
    return this.#stateByCueId.get(cueId) ?? 'none';
  }

  markPending(cueIds) {
    for (const cueId of cueIds) this.#setStateOfKnownCue(cueId, 'pending');
  }

  setTranslation(cueId, text) {
    if (!this.#stateByCueId.has(cueId)) return;
    this.#translationTextByCueId.set(cueId, text);
    this.#stateByCueId.set(cueId, 'done');
  }

  markFailed(cueIds) {
    for (const cueId of cueIds) this.#setStateOfKnownCue(cueId, 'failed');
  }

  /** Turns every pending cue back into none. */
  resetPending() {
    this.#resetStateToNone('pending');
  }

  /** Turns every failed cue back into none. */
  resetFailed() {
    this.#resetStateToNone('failed');
  }

  /** @param {Record<string,string>} translationsByCueId unknown ids are ignored */
  loadTranslations(translationsByCueId) {
    for (const [cueId, text] of Object.entries(translationsByCueId)) {
      this.setTranslation(Number(cueId), text);
    }
  }

  /** @returns {Record<string,string>} translations of done cues only */
  translationsByCueId() {
    const result = {};
    for (const [cueId, text] of this.#translationTextByCueId) {
      if (this.#stateByCueId.get(cueId) === 'done') result[cueId] = text;
    }
    return result;
  }

  /** @returns {{kind:'nothing'}|{kind:'text',text:string}|{kind:'waiting'}|{kind:'failed'}} */
  displayAt(timeMs) {
    const cue = this.cueAt(timeMs);
    if (!cue) return { kind: 'nothing' };
    const state = this.translationState(cue.id);
    if (state === 'done') return { kind: 'text', text: this.#translationTextByCueId.get(cue.id) };
    if (state === 'failed') return { kind: 'failed' };
    return { kind: 'waiting' };
  }

  /**
   * Milliseconds from timeMs to the start of the first cue at or after timeMs that is still
   * none or pending (0 when the current cue is such a cue). Failed cues count as covered.
   * Infinity when no such cue is left.
   */
  translatedAheadMs(timeMs) {
    for (let index = this.#indexOfFirstCueEndingAfter(timeMs); index < this.#cues.length; index++) {
      const cue = this.#cues[index];
      const state = this.#stateByCueId.get(cue.id);
      if (state === 'none' || state === 'pending') return Math.max(0, cue.startMs - timeMs);
    }
    return Infinity;
  }

  /** @returns {Cue[]} up to `limit` cues in state none, from the cue containing timeMs (or the next one) on */
  untranslatedFrom(timeMs, limit) {
    const untranslatedCues = [];
    for (
      let index = this.#indexOfFirstCueEndingAfter(timeMs);
      index < this.#cues.length && untranslatedCues.length < limit;
      index++
    ) {
      const cue = this.#cues[index];
      if (this.#stateByCueId.get(cue.id) === 'none') untranslatedCues.push(cue);
    }
    return untranslatedCues;
  }

  #setStateOfKnownCue(cueId, state) {
    if (this.#stateByCueId.has(cueId)) this.#stateByCueId.set(cueId, state);
  }

  #resetStateToNone(stateToReset) {
    for (const [cueId, state] of this.#stateByCueId) {
      if (state === stateToReset) this.#stateByCueId.set(cueId, 'none');
    }
  }
}
