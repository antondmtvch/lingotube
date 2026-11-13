import { watchVideoIdFromUrl } from '../shared/video_url.js';

const NAVIGATION_FINISHED_EVENT = 'yt-navigate-finish';
const AD_SHOWING_CLASS = 'ad-showing';
const PLAYER_SELECTOR = '#movie_player';

/**
 * Follows YouTube's in-page navigation and ads. YouTube changes videos without reloading
 * the page, so the video id is re-read from the URL after every `yt-navigate-finish`.
 * Both callbacks fire only on a change; the first video is reported at once.
 * @param {{document: Document, window: Window,
 *   onVideoChanged: (videoId: string|null) => void,
 *   onAdStateChanged: (isAdPlaying: boolean) => void}} options
 * @returns {{stop: () => void}}
 */
export function watchYouTubePage({ document, window, onVideoChanged, onAdStateChanged }) {
  let isStopped = false;
  let reportedVideoId;
  let isAdPlaying = false;
  let observedPlayerElement = null;
  let adObserver = null;

  const reportAdState = () => {
    const isAdPlayingNow = Boolean(observedPlayerElement?.classList.contains(AD_SHOWING_CLASS));
    if (isAdPlayingNow === isAdPlaying) return;
    isAdPlaying = isAdPlayingNow;
    onAdStateChanged(isAdPlaying);
  };

  // The player is created on the first watch page and normally kept afterwards;
  // follow it whenever the element under #movie_player changes.
  const observeCurrentPlayer = () => {
    const playerElement = document.querySelector(PLAYER_SELECTOR);
    if (playerElement === observedPlayerElement) return;
    adObserver?.disconnect();
    adObserver = null;
    observedPlayerElement = playerElement;
    if (playerElement) {
      adObserver = new window.MutationObserver(reportAdState);
      adObserver.observe(playerElement, { attributes: true, attributeFilter: ['class'] });
    }
    reportAdState();
  };

  const handleNavigation = () => {
    if (isStopped) return;
    observeCurrentPlayer();
    const videoId = watchVideoIdFromUrl(window.location.href);
    if (videoId === reportedVideoId) return;
    reportedVideoId = videoId;
    onVideoChanged(videoId);
  };

  document.addEventListener(NAVIGATION_FINISHED_EVENT, handleNavigation);
  handleNavigation();

  return {
    stop() {
      isStopped = true;
      document.removeEventListener(NAVIGATION_FINISHED_EVENT, handleNavigation);
      adObserver?.disconnect();
      adObserver = null;
    },
  };
}
