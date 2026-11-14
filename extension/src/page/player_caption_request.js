// The caption URL and its `pot` token never leave the MAIN world and are never logged.

const YOUTUBE_ORIGIN = 'https://www.youtube.com';
const POLL_INTERVAL_MS = 100;
const GRACE_PERIOD_MS = 300;
const BUTTON_STATE_SETTLE_MS = 300;
const RESTORE_PAUSE_MS = 500;
// The player may ask for captions before its pot token is ready; that request has no pot and gets
// an empty body. Turning subtitles off and on again makes it ask once more, then with the token.
const MAX_TURN_ON_ATTEMPTS = 3;
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

/** The player asked for this video's captions before its pot token was ready. */
function isCaptionRequestWithoutPotForVideo(resourceUrl, videoId) {
  try {
    const url = new URL(resourceUrl, YOUTUBE_ORIGIN);
    return url.pathname.includes('/api/timedtext') && !url.searchParams.has('pot') && url.searchParams.get('v') === videoId;
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
 * the subtitles button if there is none. The button is returned to its original state.
 * Two captures must never run at once on the same button: use createSerialCaptionCapture.
 * @param {object} options
 * @param {Element} options.playerElement the visible player; its own subtitles button is the one clicked
 * @param {typeof PerformanceObserver} options.performanceObserverClass
 * @param {(ms: number) => Promise<void>} options.sleep
 * @param {string} options.expectedVideoId only requests for this video count
 * @param {number} [options.timeoutMs]
 * @param {(message: string, details: object) => void} [options.logInfo] diagnostics; never gets a URL
 * @returns {Promise<string|null>}
 */
export async function capturePlayerCaptionRequestUrl({
  playerElement,
  performanceObserverClass,
  sleep,
  expectedVideoId,
  timeoutMs = 6000,
  logInfo = () => {},
}) {
  let capturedUrl = null;
  let hasPotlessRequestForThisVideo = false;
  const observer = new performanceObserverClass((list) => {
    for (const entry of list.getEntries()) {
      if (isCaptionRequestWithoutPotForVideo(entry.name, expectedVideoId)) hasPotlessRequestForThisVideo = true;
      if (isPlayerCaptionRequestForVideo(entry.name, expectedVideoId)) capturedUrl = entry.name;
    }
  });
  observer.observe({ type: 'resource', buffered: true });

  const waitForRequest = async (limitMs) => {
    for (let waitedMs = 0; !capturedUrl && waitedMs < limitMs; waitedMs += POLL_INTERVAL_MS) {
      await sleep(POLL_INTERVAL_MS);
    }
  };

  const button = playerElement?.querySelector('.ytp-subtitles-button');
  const wasOn = button?.getAttribute('aria-pressed') === 'true';
  let buttonUsed = false;
  let turnOns = 0;
  try {
    await waitForRequest(GRACE_PERIOD_MS);
    if (!capturedUrl && button) {
      buttonUsed = true;
      await activateSubtitleButton(button, sleep);
      if (wasOn) await activateSubtitleButton(button, sleep);
      turnOns = 1;
      await waitForRequest(timeoutMs);
      // Only a request without pot is worth another try; with no request at all the button is not the way.
      for (let turnOn = 2; !capturedUrl && hasPotlessRequestForThisVideo && turnOn <= MAX_TURN_ON_ATTEMPTS; turnOn += 1) {
        await activateSubtitleButton(button, sleep);
        await activateSubtitleButton(button, sleep);
        turnOns = turnOn;
        await waitForRequest(timeoutMs);
      }
    }
  } finally {
    observer.disconnect();
    if (buttonUsed) {
      const isOnNow = button.getAttribute('aria-pressed') === 'true';
      if (isOnNow !== wasOn) await activateSubtitleButton(button, sleep);
      await sleep(RESTORE_PAUSE_MS);
    }
    if (buttonUsed) {
      logInfo('lingotube: caption capture', { turnOns, requestWithoutPotSeen: hasPotlessRequestForThisVideo, captured: Boolean(capturedUrl) });
    }
  }
  return capturedUrl;
}

/**
 * Wraps a capture so that calls run one after another, each starting only after the previous
 * one has restored the button (its `finally` finished). A capture of a video the user already
 * left still runs to the end; only its result is ignored by the caller.
 * @param {(options: object) => Promise<string|null>} [capture]
 * @returns {(options: object) => Promise<string|null>}
 */
export function createSerialCaptionCapture(capture = capturePlayerCaptionRequestUrl) {
  let previousCapture = Promise.resolve();
  return (options) => {
    const result = previousCapture.then(() => capture(options));
    // The chain only orders the captures; each caller still sees its own result or error.
    previousCapture = result.catch(() => {});
    return result;
  };
}
