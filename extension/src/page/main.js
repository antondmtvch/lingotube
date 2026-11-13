// Entry of the page bundle (MAIN world): builds every component once per page and wires them.
// Tokens, chat commands and the authorization header never leave this world and are never
// logged; logs carry no URL, token or video id.

import { openAskChat } from './ask_chat_client.js';
import { ChatRequestGate } from './chat_request_gate.js';
import { ChatTranslator } from './chat_translator.js';
import { createExtensionStorage } from './extension_storage.js';
import { OverlayView } from './overlay_view.js';
import { createSerialCaptionCapture } from './player_caption_request.js';
import { PlayerControls } from './player_controls.js';
import { SettingsStore, createSettingsSaver, loadSettingsWithRetries } from './settings_store.js';
import { SubtitleSession } from './subtitle_session.js';
import { TranslationCache } from './translation_cache.js';
import { CaptionsUnavailableError, fetchCaptionWords } from './youtube_captions_source.js';
import { watchYouTubePage } from './youtube_page_watcher.js';
import { findPlayerElement, readCaptionTracks, readVideoDetails } from './youtube_player.js';
import { captionSourceKey } from '../shared/cache_key.js';
import { chooseCaptionTrack } from '../shared/caption_track_choice.js';
import { rememberTypedLanguage } from '../shared/player_panel_logic.js';
import { DEFAULT_CUE_RULES, buildCues } from '../shared/sentence_cues.js';

const PLAYER_POLL_INTERVAL_MS = 250;
const PLAYER_WAIT_LIMIT_MS = 15000;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Hex SHA-1 for the SAPISIDHASH header, computed by the page's WebCrypto. */
async function sha1Hex(text) {
  const digest = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

/** Only the error name: messages of foreign errors may hold request data. */
function reportUnexpectedError(error) {
  console.error('lingotube: unexpected error', error?.name ?? 'unknown');
}

/** The chat request gate over the page's own lock manager, localStorage and visibility. */
function createChatRequestGate({ window, document }) {
  const lockManager = window.navigator?.locks ?? { request: (name, callback) => callback() };
  return new ChatRequestGate({
    lockManager,
    // localStorage itself may throw (blocked site data); the gate treats a throw as "unavailable".
    keyValueStorage: {
      getItem: (key) => window.localStorage.getItem(key),
      setItem: (key, value) => window.localStorage.setItem(key, value),
      removeItem: (key) => window.localStorage.removeItem(key),
    },
    isTabVisible: () => document.visibilityState === 'visible',
    waitUntilTabVisible: () => new Promise((resolve) => {
      const handleVisibilityChange = () => {
        if (document.visibilityState !== 'visible') return;
        document.removeEventListener('visibilitychange', handleVisibilityChange);
        resolve();
      };
      document.addEventListener('visibilitychange', handleVisibilityChange);
    }),
    now: () => Date.now(),
    sleep,
  });
}

/**
 * Waits until the player shows the given video (YouTube swaps the player data some time after
 * the navigation event). Resolves null on timeout or when `isStillWanted` turns false.
 */
async function waitForPlayerOfVideo({ document, videoId, isStillWanted }) {
  for (let waitedMs = 0; waitedMs <= PLAYER_WAIT_LIMIT_MS; waitedMs += PLAYER_POLL_INTERVAL_MS) {
    if (!isStillWanted()) return null;
    const playerElement = findPlayerElement(document);
    if (playerElement && readVideoDetails(playerElement).videoId === videoId) return playerElement;
    await sleep(PLAYER_POLL_INTERVAL_MS);
  }
  return null;
}

/**
 * Cues of the playing video from its YouTube caption track: the player's own caption request is
 * captured once (slow: grace period plus timeout), then the chosen track is fetched as json3.
 */
async function loadYouTubeCues({ window, playerElement, videoId, captureSerially }) {
  const track = chooseCaptionTrack(readCaptionTracks(playerElement));
  if (!track) throw new CaptionsUnavailableError('The video has no usable caption track');
  const playerRequestUrl = await captureSerially({
    playerElement,
    expectedVideoId: videoId,
    performanceObserverClass: window.PerformanceObserver,
    sleep,
  });
  if (!playerRequestUrl) throw new CaptionsUnavailableError('The player caption request was not captured');
  const words = await fetchCaptionWords({ track, playerRequestUrl, fetch: window.fetch.bind(window) });
  return { cues: buildCues(words, DEFAULT_CUE_RULES), sourceKey: captionSourceKey(track) };
}

/** Builds the page-lifetime components and reacts to navigation, ads and the player panel. */
function startLingotubePage({ window, document }) {
  const extensionStorage = createExtensionStorage({ window });
  const settingsStore = new SettingsStore(extensionStorage);
  // One cache and one gate for the page lifetime, shared by every session.
  const translationCache = new TranslationCache(extensionStorage);
  const chatRequestGate = createChatRequestGate({ window, document });
  const settingsLoading = loadSettingsWithRetries(settingsStore, { sleep });
  const saveSettingsChange = createSettingsSaver(settingsStore);
  // One capture at a time on the page: a stale capture of the previous video must finish
  // restoring the subtitles button before the next capture reads its state.
  const captureSerially = createSerialCaptionCapture();

  let settings = null;
  let currentVideoId = null;
  let isAdPlaying = false;
  let navigationCount = 0;
  let subtitlesGeneration = 0;
  let playerControls = null;
  let playerElementWithControls = null;
  /** @type {{session: SubtitleSession, overlayView: OverlayView}|null} */
  let activeSubtitles = null;
  /** Cues of one video, kept so a language change does not capture the player request again. */
  let cuesLoadOfVideo = null;

  const readYouTubeConfig = (name) => window.ytcfg?.get?.(name);

  function showSessionStatus(statusText, canRetry) {
    playerControls?.setStatusLine(statusText);
    playerControls?.setRetryButtonVisible(canRetry);
  }

  /**
   * Applies changes to the page at once and stores only the changed fields.
   * @param {object} changes the new values, applied to the in-memory settings
   * @param {(stored: object) => object} [computeStoredChanges] what to store, computed from the
   *   freshly loaded stored settings; by default `changes` itself
   */
  function changeSettings(changes, computeStoredChanges = () => changes) {
    settings = { ...settings, ...changes };
    playerControls?.applySettings(settings);
    saveSettingsChange(computeStoredChanges);
  }

  function loadCuesOfVideo(videoId, playerElement) {
    if (cuesLoadOfVideo?.videoId === videoId) return cuesLoadOfVideo.promise;
    const load = { videoId, promise: loadYouTubeCues({ window, playerElement, videoId, captureSerially }) };
    cuesLoadOfVideo = load;
    load.promise.catch(() => {
      if (cuesLoadOfVideo === load) cuesLoadOfVideo = null;
    });
    return load.promise;
  }

  async function createTranslator(videoId, languageName) {
    const chatSession = await openAskChat({
      videoId,
      context: readYouTubeConfig('INNERTUBE_CONTEXT'),
      sessionIndex: Number(readYouTubeConfig('SESSION_INDEX')) || 0,
      fetch: window.fetch.bind(window),
      gate: chatRequestGate,
      cookieText: document.cookie,
      now: () => Date.now(),
      sha1Hex,
    });
    return new ChatTranslator({ chatSession, languageName });
  }

  function stopSubtitles() {
    subtitlesGeneration += 1;
    if (activeSubtitles) {
      activeSubtitles.session.stop();
      activeSubtitles.overlayView.destroy();
      activeSubtitles = null;
    }
    showSessionStatus(null, false);
  }

  /** (Re)starts the subtitles of the current video with the current settings. */
  async function startSubtitles() {
    stopSubtitles();
    const generation = subtitlesGeneration;
    const videoId = currentVideoId;
    if (videoId === null || !settings?.enabled) return;
    const playerElement = await waitForPlayerOfVideo({
      document,
      videoId,
      isStillWanted: () => generation === subtitlesGeneration,
    });
    if (!playerElement || generation !== subtitlesGeneration) return;
    if (readVideoDetails(playerElement).isLive) return;

    const findVideoElement = () => playerElement.querySelector('video');
    const overlayView = new OverlayView({
      document,
      containerElement: playerElement,
      position: settings.overlayPosition,
      textScale: settings.textScale,
      onPositionChanged: (position) => changeSettings({ overlayPosition: position }),
    });
    const session = new SubtitleSession({
      videoId,
      language: settings.language,
      loadCues: () => loadCuesOfVideo(videoId, playerElement),
      createTranslator: (languageName) => createTranslator(videoId, languageName),
      cache: translationCache,
      overlayView,
      getPositionMs: () => (findVideoElement()?.currentTime ?? 0) * 1000,
      isPaused: () => findVideoElement()?.paused ?? true,
      setTimer: (callback, intervalMs) => setInterval(callback, intervalMs),
      clearTimer: (handle) => clearInterval(handle),
      onStatusChanged: (statusText, { canRetry }) => showSessionStatus(statusText, canRetry),
      logInfo: (message, details) => console.info(message, details),
    });
    activeSubtitles = { session, overlayView };
    session.setAdPlaying(isAdPlaying);
    await session.start();
  }

  function attachPlayerControls(playerElement) {
    if (playerElementWithControls === playerElement) return;
    playerControls?.destroy();
    playerElementWithControls = playerElement;
    playerControls = new PlayerControls({
      document,
      playerElement,
      settings,
      onEnabledChanged: (isEnabled) => {
        changeSettings({ enabled: isEnabled });
        if (isEnabled) startSubtitles().catch(reportUnexpectedError);
        else stopSubtitles();
      },
      onLanguageChanged: (language) => {
        if (language.code === settings.language.code && language.name === settings.language.name) return;
        // The stored list is rebuilt from the stored names, not this page's copy, so names
        // remembered by another tab are kept.
        changeSettings(
          { language, customLanguageNames: rememberTypedLanguage(settings.customLanguageNames, language) },
          (stored) => ({ language, customLanguageNames: rememberTypedLanguage(stored.customLanguageNames, language) }),
        );
        if (settings.enabled) startSubtitles().catch(reportUnexpectedError);
      },
      onTextScaleChanged: (scale) => {
        changeSettings({ textScale: scale });
        activeSubtitles?.overlayView.setTextScale(scale);
      },
      onRetryRequested: () => {
        chatRequestGate.clearCooldown();
        activeSubtitles?.session.retry();
      },
    });
  }

  async function openVideo(videoId) {
    navigationCount += 1;
    const navigation = navigationCount;
    currentVideoId = videoId;
    // The old session goes first: a late chat reply of the old video never reaches the new one.
    stopSubtitles();
    if (videoId === null) return;
    if (settings === null) settings = await settingsLoading;
    const playerElement = await waitForPlayerOfVideo({
      document,
      videoId,
      isStillWanted: () => navigation === navigationCount,
    });
    if (!playerElement || navigation !== navigationCount) return;
    attachPlayerControls(playerElement);
    if (settings.enabled) await startSubtitles();
  }

  watchYouTubePage({
    document,
    window,
    onVideoChanged: (videoId) => {
      openVideo(videoId).catch(reportUnexpectedError);
    },
    onAdStateChanged: (isAdPlayingNow) => {
      isAdPlaying = isAdPlayingNow;
      activeSubtitles?.session.setAdPlaying(isAdPlayingNow);
    },
  });
}

startLingotubePage({ window, document });
