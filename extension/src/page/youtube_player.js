/** @returns {HTMLElement|null} */
export function findPlayerElement(document) {
  return document.querySelector('#movie_player');
}

/**
 * @param {HTMLElement} playerElement
 * @returns {import('../shared/caption_track_choice.js').CaptionTrackInfo[]}
 */
export function readCaptionTracks(playerElement) {
  const tracks =
    playerElement.getPlayerResponse?.()?.captions?.playerCaptionsTracklistRenderer?.captionTracks ?? [];
  return tracks.map((track) => ({
    languageCode: track.languageCode,
    kind: track.kind === 'asr' ? 'asr' : 'manual',
    baseUrl: track.baseUrl,
  }));
}

/**
 * @param {HTMLElement} playerElement
 * @returns {{videoId: string, durationMs: number, isLive: boolean}}
 */
export function readVideoDetails(playerElement) {
  const details = playerElement.getPlayerResponse?.()?.videoDetails ?? {};
  return {
    videoId: details.videoId ?? '',
    durationMs: Number(details.lengthSeconds ?? 0) * 1000,
    isLive: Boolean(details.isLive),
  };
}
