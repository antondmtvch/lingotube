/** How long the video may be held while a translation is pending. */
export const WAIT_CAP_MS = 30000;

/**
 * @typedef {object} WaitDecision
 * @property {'pause'|'play'|'none'} action What the caller must do with the video.
 * @property {boolean} isCapped Whether the wait cap has been reached for this wait.
 * @property {boolean} pausedByUs Whether the video is paused by us after the action.
 */

/**
 * Decide whether to pause or resume the video while subtitles are translating.
 * Pure: no timers, no DOM; the caller supplies the clock and applies the result.
 *
 * @param {object} state
 * @param {boolean} state.isEnabled The waitForSubtitles setting.
 * @param {boolean} state.isWaiting The status shows "translating" right now.
 * @param {boolean} state.isAdPlaying An ad is playing.
 * @param {boolean} state.isPumpStopped Translation stopped for a reason.
 * @param {boolean} state.isAtVideoEnd Position is at or past the duration.
 * @param {boolean} state.isVideoPaused The video element is paused right now.
 * @param {boolean} state.pausedByUs We paused the video and the pause is still ours.
 * @param {number|null} state.waitStartedMs When the current wait began.
 * @param {boolean} state.isCapped The cap already expired for this wait.
 * @param {boolean} [state.isDismissedByUser] The user resumed over our pause: no new pause in this wait.
 * @param {number} state.nowMs The current time.
 * @returns {WaitDecision}
 */
export function decideWaitAction({
  isEnabled,
  isWaiting,
  isAdPlaying,
  isPumpStopped,
  isAtVideoEnd,
  isVideoPaused,
  pausedByUs,
  waitStartedMs,
  isCapped,
  isDismissedByUser = false,
  nowMs,
}) {
  // The user or YouTube resumed the video: our pause is gone.
  if (pausedByUs && !isVideoPaused) {
    return { action: 'none', isCapped, pausedByUs: false };
  }
  const mustNotHold = !isWaiting || isAdPlaying || !isEnabled || isPumpStopped || isAtVideoEnd;
  if (pausedByUs && mustNotHold) {
    return { action: 'play', isCapped, pausedByUs: false };
  }
  if (!isWaiting) {
    return { action: 'none', isCapped: false, pausedByUs };
  }
  if (isCapped) {
    return { action: 'none', isCapped: true, pausedByUs };
  }
  if (isAdPlaying || !isEnabled || isPumpStopped || isAtVideoEnd) {
    return { action: 'none', isCapped, pausedByUs };
  }
  const isCapReached = waitStartedMs !== null && nowMs - waitStartedMs >= WAIT_CAP_MS;
  if (isCapReached) {
    // Release our own pause at the cap, otherwise the video would stay held.
    return { action: pausedByUs ? 'play' : 'none', isCapped: true, pausedByUs: false };
  }
  if (isDismissedByUser) {
    return { action: 'none', isCapped, pausedByUs };
  }
  if (!isVideoPaused) {
    return { action: 'pause', isCapped, pausedByUs: true };
  }
  return { action: 'none', isCapped, pausedByUs };
}
