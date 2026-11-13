// The caption URL and its `pot` token never leave the MAIN world and are never logged.

const YOUTUBE_ORIGIN = 'https://www.youtube.com';
const PLAYER_CLASS_HIDING_NATIVE_CAPTIONS = 'lingotube-hide-native-captions';
const POLL_INTERVAL_MS = 100;
const GRACE_PERIOD_MS = 300;
const BUTTON_TOGGLE_PAUSE_MS = 700;
const RESTORE_PAUSE_MS = 500;

/**
 * Takes the track's own address and adds the parameters the player sent
 * (`pot` and the client parameters). The track keeps its own lang/kind/signature;
 * `tlang` (auto translation) is dropped; the format is forced to json3.
 * @param {string} trackBaseUrl
 * @param {string} playerRequestUrl
 * @returns {string}
 */
export function mergePlayerRequestParameters(trackBaseUrl, playerRequestUrl) {
  const merged = new URL(trackBaseUrl, YOUTUBE_ORIGIN);
  const playerRequest = new URL(playerRequestUrl, YOUTUBE_ORIGIN);
  for (const [name, value] of playerRequest.searchParams) {
    if (name !== 'tlang' && !merged.searchParams.has(name)) merged.searchParams.set(name, value);
  }
  merged.searchParams.delete('tlang');
  merged.searchParams.set('fmt', 'json3');
  return merged.toString();
}

/**
 * The player's own caption requests carry `pot`; the extension's never do.
 * @param {string} resourceUrl
 * @returns {boolean}
 */
export function isPlayerCaptionRequest(resourceUrl) {
  try {
    const url = new URL(resourceUrl, YOUTUBE_ORIGIN);
    return url.pathname.includes('/api/timedtext') && url.searchParams.has('pot');
  } catch {
    return false;
  }
}

/**
 * Finds the player's caption request in the resource log, provoking one with
 * the subtitles button if there is none. Native captions are hidden by CSS
 * meanwhile, and the button is returned to its original state.
 * @param {object} options
 * @param {Document} options.document
 * @param {typeof PerformanceObserver} options.performanceObserverClass
 * @param {(ms: number) => Promise<void>} options.sleep
 * @param {number} [options.timeoutMs]
 * @param {() => void} [options.onButtonForced] called when the button had to be used
 * @returns {Promise<string|null>}
 */
export async function capturePlayerCaptionRequestUrl({
  document,
  performanceObserverClass,
  sleep,
  timeoutMs = 6000,
  onButtonForced = () => {},
}) {
  let capturedUrl = null;
  const observer = new performanceObserverClass((list) => {
    for (const entry of list.getEntries()) {
      if (isPlayerCaptionRequest(entry.name)) capturedUrl = entry.name;
    }
  });
  observer.observe({ type: 'resource', buffered: true });

  const waitForRequest = async (limitMs) => {
    for (let waitedMs = 0; !capturedUrl && waitedMs < limitMs; waitedMs += POLL_INTERVAL_MS) {
      await sleep(POLL_INTERVAL_MS);
    }
  };

  const player = document.querySelector('#movie_player');
  const button = document.querySelector('.ytp-subtitles-button');
  const wasOn = button?.getAttribute('aria-pressed') === 'true';
  let buttonUsed = false;
  try {
    await waitForRequest(GRACE_PERIOD_MS);
    if (!capturedUrl && button) {
      buttonUsed = true;
      onButtonForced();
      player?.classList.add(PLAYER_CLASS_HIDING_NATIVE_CAPTIONS);
      if (wasOn) {
        button.click();
        await sleep(BUTTON_TOGGLE_PAUSE_MS);
      }
      button.click();
      await waitForRequest(timeoutMs);
    }
  } finally {
    observer.disconnect();
    if (buttonUsed) {
      const isOnNow = button.getAttribute('aria-pressed') === 'true';
      if (isOnNow !== wasOn) button.click();
      await sleep(RESTORE_PAUSE_MS);
      player?.classList.remove(PLAYER_CLASS_HIDING_NATIVE_CAPTIONS);
    }
  }
  return capturedUrl;
}
