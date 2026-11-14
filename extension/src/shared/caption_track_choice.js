/**
 * @typedef {{languageCode: string, kind: 'asr'|'manual', baseUrl: string, name?: string}} CaptionTrackInfo
 */

/**
 * Picks the caption track to take words from (spec section 8).
 * The original language is the language of the first automatic ("asr") track.
 * @param {CaptionTrackInfo[]} tracks
 * @returns {CaptionTrackInfo|null}
 */
export function chooseCaptionTrack(tracks) {
  const firstAutomaticTrack = tracks.find((track) => track.kind === 'asr');
  if (!firstAutomaticTrack) {
    return tracks.find((track) => track.kind === 'manual') ?? null;
  }
  const originalLanguage = firstAutomaticTrack.languageCode;
  const manualTrackInOriginalLanguage = tracks.find(
    (track) => track.kind === 'manual' && track.languageCode === originalLanguage,
  );
  return manualTrackInOriginalLanguage ?? firstAutomaticTrack;
}
