// The caption URL and its `pot` token never leave the MAIN world and are never logged.

const YOUTUBE_ORIGIN = 'https://www.youtube.com';
const PLAYER_CLASS_HIDING_NATIVE_CAPTIONS = 'lingotube-hide-native-captions';
const POLL_INTERVAL_MS = 100;
const GRACE_PERIOD_MS = 300;
const BUTTON_STATE_SETTLE_MS = 300;
const RESTORE_PAUSE_MS = 500;
// Parameters that identify the track: the track URL keeps its own, never the player's.
const TRACK_IDENTITY_PARAMETERS = new Set(['lang', 'kind', 'name', 'tlang']);

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
    if (!TRACK_IDENTITY_PARAMETERS.has(name) && !merged.searchParams.has(name)) merged.searchParams.set(name, value);
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

function isPlayerCaptionRequestForVideo(resourceUrl, videoId) {
  return (
    isPlayerCaptionRequest(resourceUrl) &&
    new URL(resourceUrl, YOUTUBE_ORIGIN).searchParams.get('v') === videoId
  );
}

/**
 * Counts, without exposing any value, why a player caption request may not match.
 * Returns only booleans and numbers: never a URL, a query value or a video id.
 * @param {Element|null} playerElement
 * @param {string} expectedVideoId
 * @param {Array<{name: string}>} resourceEntries
 * @returns {Record<string, number|boolean>}
 */
export function captureDiagnostics(playerElement, expectedVideoId, resourceEntries = performance.getEntriesByType('resource')) {
  let timedtextEntriesSeen = 0;
  let timedtextWithPot = 0;
  let timedtextWithMatchingVideo = 0;
  let timedtextWithAnyV = 0;
  for (const entry of resourceEntries) {
    if (!String(entry.name).includes('/api/timedtext')) continue;
    timedtextEntriesSeen += 1;
    try {
      const { searchParams } = new URL(entry.name, YOUTUBE_ORIGIN);
      if (searchParams.has('pot')) timedtextWithPot += 1;
      if (searchParams.has('v')) timedtextWithAnyV += 1;
      if (searchParams.get('v') === expectedVideoId) timedtextWithMatchingVideo += 1;
    } catch {
      // An unparsable address only counts as seen.
    }
  }
  return {
    expectedVideoIdLength: expectedVideoId.length,
    timedtextEntriesSeen,
    timedtextWithPot,
    timedtextWithMatchingVideo,
    timedtextWithAnyV,
    playerHasGetPlayerResponse: typeof playerElement?.getPlayerResponse === 'function',
    subtitlesButtonFound: Boolean(playerElement?.querySelector?.('.ytp-subtitles-button')),
  };
}

/**
 * Presses the subtitles button the way a real click does: a pointer and mouse
 * sequence dispatched on the button. A bare `.click()` does not toggle the
 * player's button, so it is only a last resort when the state did not change.
 * @param {Element} button
 * @param {(ms: number) => Promise<void>} sleep
 * @returns {Promise<{pressedAfterSequence: boolean, pressedAfterActivation: boolean, fallbackUsed: boolean}>}
 */
export async function activateSubtitleButton(button, sleep) {
  const readPressed = () => button.getAttribute('aria-pressed') === 'true';
  const pressedBefore = readPressed();
  const box = button.getBoundingClientRect?.();
  const coordinates = box
    ? { clientX: box.left + box.width / 2, clientY: box.top + box.height / 2 }
    : {};
  const eventOptions = { bubbles: true, cancelable: true, composed: true, button: 0, ...coordinates };
  const PointerEventClass = typeof PointerEvent === 'function' ? PointerEvent : MouseEvent;
  button.dispatchEvent(new PointerEventClass('pointerdown', { ...eventOptions, pointerType: 'mouse' }));
  button.dispatchEvent(new MouseEvent('mousedown', eventOptions));
  button.dispatchEvent(new MouseEvent('mouseup', eventOptions));
  button.dispatchEvent(new MouseEvent('click', eventOptions));
  await sleep(BUTTON_STATE_SETTLE_MS);
  const pressedAfterSequence = readPressed();
  let fallbackUsed = false;
  if (pressedAfterSequence === pressedBefore) {
    fallbackUsed = true;
    button.click();
    await sleep(BUTTON_STATE_SETTLE_MS);
  }
  return { pressedAfterSequence, pressedAfterActivation: readPressed(), fallbackUsed };
}

/**
 * Finds the player's caption request in the resource log, provoking one with
 * the subtitles button if there is none. Native captions are hidden by CSS
 * meanwhile, and the button is returned to its original state.
 * @param {object} options
 * @param {Document} options.document only used to count subtitles buttons for diagnostics
 * @param {Element} options.playerElement the visible player; its own subtitles button is the one clicked
 * @param {typeof PerformanceObserver} options.performanceObserverClass
 * @param {(ms: number) => Promise<void>} options.sleep
 * @param {string} options.expectedVideoId only requests for this video count
 * @param {number} [options.timeoutMs]
 * @param {() => void} [options.onButtonForced] called when the button had to be used
 * @param {(observation: Record<string, number|boolean>) => void} [options.onButtonObserved]
 *   receives only booleans and numbers about the button, never a value or a URL
 * @returns {Promise<string|null>}
 */
export async function capturePlayerCaptionRequestUrl({
  document,
  playerElement,
  performanceObserverClass,
  sleep,
  expectedVideoId,
  timeoutMs = 6000,
  onButtonForced = () => {},
  onButtonObserved = () => {},
}) {
  let capturedUrl = null;
  const observer = new performanceObserverClass((list) => {
    for (const entry of list.getEntries()) {
      if (isPlayerCaptionRequestForVideo(entry.name, expectedVideoId)) capturedUrl = entry.name;
    }
  });
  observer.observe({ type: 'resource', buffered: true });

  const waitForRequest = async (limitMs) => {
    for (let waitedMs = 0; !capturedUrl && waitedMs < limitMs; waitedMs += POLL_INTERVAL_MS) {
      await sleep(POLL_INTERVAL_MS);
    }
  };

  const player = playerElement;
  const button = playerElement?.querySelector('.ytp-subtitles-button');
  const wasOn = button?.getAttribute('aria-pressed') === 'true';
  const buttonObservation = {
    subtitleButtonCountInPlayer: playerElement?.querySelectorAll?.('.ytp-subtitles-button').length ?? 0,
    subtitleButtonCountInDocument: document?.querySelectorAll?.('.ytp-subtitles-button').length ?? 0,
    subtitleButtonPressedBefore: wasOn,
  };
  let buttonUsed = false;
  try {
    await waitForRequest(GRACE_PERIOD_MS);
    if (!capturedUrl && button) {
      buttonUsed = true;
      onButtonForced();
      player?.classList.add(PLAYER_CLASS_HIDING_NATIVE_CAPTIONS);
      const firstActivation = await activateSubtitleButton(button, sleep);
      buttonObservation.subtitleButtonPressedAfterFirstClick = firstActivation.pressedAfterSequence;
      let lastActivation = firstActivation;
      let activationFallbackUsed = firstActivation.fallbackUsed;
      if (wasOn) {
        lastActivation = await activateSubtitleButton(button, sleep);
        activationFallbackUsed ||= lastActivation.fallbackUsed;
      }
      buttonObservation.subtitleButtonPressedAfterActivation = lastActivation.pressedAfterActivation;
      buttonObservation.activationFallbackUsed = activationFallbackUsed;
      onButtonObserved(buttonObservation);
      await waitForRequest(timeoutMs);
    }
  } finally {
    observer.disconnect();
    if (buttonUsed) {
      const isOnNow = button.getAttribute('aria-pressed') === 'true';
      if (isOnNow !== wasOn) await activateSubtitleButton(button, sleep);
      await sleep(RESTORE_PAUSE_MS);
      player?.classList.remove(PLAYER_CLASS_HIDING_NATIVE_CAPTIONS);
    }
  }
  return capturedUrl;
}
