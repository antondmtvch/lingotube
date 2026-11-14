// Safe pause/resume of the page's <video> on behalf of one subtitle session. No pause policy
// lives here: the session decides when; this only refuses calls that would hit the wrong state.

/**
 * @param {{findVideoElement: () => (HTMLVideoElement|null|undefined),
 *   readShownVideoId: () => string,
 *   sessionVideoId: string}} options
 *   readShownVideoId: id of the video the player shows now; calls of a session whose video is
 *   no longer shown (the session was stopped by navigation) must not touch the player.
 * @returns {{pause: () => void, play: () => void}}
 */
export function createVideoPlayback({ findVideoElement, readShownVideoId, sessionVideoId }) {
  const findVideoOfSession = () =>
    readShownVideoId() === sessionVideoId ? (findVideoElement() ?? null) : null;
  return {
    pause() {
      findVideoOfSession()?.pause();
    },
    play() {
      const video = findVideoOfSession();
      // An ended video would restart from the beginning on play().
      if (!video || !video.paused || video.ended) return;
      // The browser may refuse to play; that is not an error of ours.
      Promise.resolve(video.play()).catch(() => {});
    },
  };
}
