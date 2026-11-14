/** @typedef {import('./cue_track.js').CueTrack} CueTrack */
/** @typedef {import('./sentence_cues.js').Cue} Cue */

/** How far ahead of playback cues stay translated, and how many cues one chat message carries. */
export const DEFAULT_SCHEDULE = { reserveAheadMs: 120000, batchSize: 30 };

/**
 * Picks the cues to translate next: none while the translated reserve ahead of the
 * playhead is large enough, otherwise the next untranslated cues from the playhead on.
 * @param {CueTrack} track
 * @param {number} positionMs playhead position
 * @param {{reserveAheadMs: number, batchSize: number}} schedule
 * @returns {Cue[]}
 */
export function chooseNextBatch(track, positionMs, schedule = DEFAULT_SCHEDULE) {
  if (track.translatedAheadMs(positionMs) >= schedule.reserveAheadMs) return [];
  return track.untranslatedFrom(positionMs, schedule.batchSize);
}
