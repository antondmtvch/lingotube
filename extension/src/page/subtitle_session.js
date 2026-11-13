import { translationCacheKey } from '../shared/cache_key.js';
import { ChatRateLimitedError } from '../shared/chat_errors.js';
import { CueTrack } from '../shared/cue_track.js';
import { promptLanguageName } from '../shared/language_choices.js';
import { STATUS_TEXTS, rateLimitedText } from '../shared/status_texts.js';
import { TranslationPump } from '../shared/translation_pump.js';
import { DEFAULT_SCHEDULE } from '../shared/translation_schedule.js';

/** @typedef {import('../shared/sentence_cues.js').Cue} Cue */

const TICK_INTERVAL_MS = 250;
const MS_PER_MINUTE = 60000;

const STATUS_TEXT_BY_STOP_REASON = {
  'not-signed-in': STATUS_TEXTS.notSignedIn,
  'chat-unavailable': STATUS_TEXTS.chatUnavailable,
  'repeated-failures': STATUS_TEXTS.repeatedFailures,
};

/**
 * Translated subtitles of ONE video in ONE language: loads the cues, restores cached
 * translations, and on a 250 ms timer shows the cue under the playhead and lets the pump
 * translate ahead. A new video or language gets a new session; after stop() nothing of
 * this session reaches the view, the status callback or the cache.
 */
export class SubtitleSession {
  #videoId;
  #language;
  #languageName;
  #loadCues;
  #createTranslator;
  #cache;
  #overlayView;
  #getPositionMs;
  #isPaused;
  #setTimer;
  #clearTimer;
  #onStatusChanged;
  #logInfo;
  #now;
  #schedule;

  #isStarted = false;
  #isStopped = false;
  #isAdPlaying = false;
  #timerHandle = null;
  #track = null;
  #pump = null;
  #cacheKey = null;
  #translator = null;
  #rateLimitedUntilMs = null;
  /** Shown in the box instead of "Перевожу…" while the pump is stopped by an error. */
  #stopStatusText = null;
  #lastRenderedKey = null;

  /**
   * @param {{
   *   videoId: string,
   *   language: import('../shared/language_choices.js').TargetLanguage,
   *   loadCues: () => Promise<{cues: Cue[], sourceKey: string}>,
   *   createTranslator: (languageName: string) => Promise<{translateCues: Function}>,
   *   cache: {load: (key: string) => Promise<object|null>, save: (key: string, entry: object) => Promise<void>},
   *   overlayView: {showCueText: Function, showStatus: Function, clear: Function, setHidden: Function},
   *   getPositionMs: () => number,
   *   isPaused?: () => boolean,
   *   setTimer: (callback: () => void, intervalMs: number) => any,
   *   clearTimer: (handle: any) => void,
   *   onStatusChanged: (statusText: string|null, details: {canRetry: boolean}) => void,
   *   logInfo?: (message: string, details: object) => void,
   *   now?: () => number,
   *   schedule?: {reserveAheadMs: number, batchSize: number},
   * }} options
   */
  constructor({
    videoId,
    language,
    loadCues,
    createTranslator,
    cache,
    overlayView,
    getPositionMs,
    isPaused = () => false,
    setTimer,
    clearTimer,
    onStatusChanged,
    logInfo = () => {},
    now = () => Date.now(),
    schedule = DEFAULT_SCHEDULE,
  }) {
    this.#videoId = videoId;
    this.#language = language;
    this.#languageName = promptLanguageName(language);
    this.#loadCues = loadCues;
    this.#createTranslator = createTranslator;
    this.#cache = cache;
    this.#overlayView = overlayView;
    this.#getPositionMs = getPositionMs;
    this.#isPaused = isPaused;
    this.#setTimer = setTimer;
    this.#clearTimer = clearTimer;
    this.#onStatusChanged = onStatusChanged;
    this.#logInfo = logInfo;
    this.#now = now;
    this.#schedule = schedule;
  }

  /** Loads the cues and cached translations, then starts the timer. Never rejects. */
  async start() {
    if (this.#isStarted || this.#isStopped) return;
    this.#isStarted = true;
    if (!this.#isAdPlaying) this.#overlayView.showStatus(STATUS_TEXTS.translating);

    let loaded = null;
    try {
      loaded = await this.#loadCues();
    } catch {
      loaded = null;
    }
    if (this.#isStopped) return;
    if (!loaded || !Array.isArray(loaded.cues) || loaded.cues.length === 0) {
      // Task 13 adds the chat transcript fallback here, behind the same loadCues seam.
      this.#overlayView.clear();
      this.#onStatusChanged(STATUS_TEXTS.captionsNotFetched, { canRetry: false });
      return;
    }

    this.#track = new CueTrack(loaded.cues);
    this.#cacheKey = translationCacheKey({
      videoId: this.#videoId,
      language: this.#language,
      sourceKey: loaded.sourceKey,
    });
    const cachedEntry = await this.#loadCachedEntry();
    if (this.#isStopped) return;
    if (cachedEntry) this.#track.loadTranslations(cachedEntry.translations);

    this.#pump = new TranslationPump({
      track: this.#track,
      translator: { translateCues: (cues) => this.#translateCues(cues) },
      getPositionMs: this.#getPositionMs,
      schedule: this.#schedule,
      onTranslationsChanged: () => this.#saveTranslations(),
      onStopped: (reason) => this.#handlePumpStopped(reason),
    });
    this.#logInfo('lingotube: session started', {
      cues: loaded.cues.length,
      cachedTranslations: Object.keys(this.#track.translationsByCueId()).length,
    });
    this.#lastRenderedKey = null;
    this.#timerHandle = this.#setTimer(() => this.#tick(), TICK_INTERVAL_MS);
    this.#tick();
  }

  /** Idempotent: stops the timer and the pump; late chat replies are discarded. */
  stop() {
    if (this.#isStopped) return;
    this.#isStopped = true;
    if (this.#timerHandle !== null) this.#clearTimer(this.#timerHandle);
    this.#timerHandle = null;
    this.#pump?.stop();
  }

  /** The "retry" action: resumes a pump stopped by an error and re-schedules failed cues. */
  retry() {
    if (this.#isStopped || !this.#pump) return;
    this.#pump.resume();
    this.#track.resetFailed();
    this.#rateLimitedUntilMs = null;
    this.#stopStatusText = null;
    this.#lastRenderedKey = null;
    this.#onStatusChanged(null, { canRetry: false });
  }

  /**
   * While an ad plays the box is emptied and hidden and nothing ticks (the video position is
   * the ad's). The box is emptied first, so un-hiding it after the ad never shows stale text.
   * @param {boolean} isAdPlaying
   */
  setAdPlaying(isAdPlaying) {
    if (this.#isStopped || isAdPlaying === this.#isAdPlaying) return;
    this.#isAdPlaying = isAdPlaying;
    this.#lastRenderedKey = null;
    if (isAdPlaying) this.#overlayView.clear();
    this.#overlayView.setHidden(isAdPlaying);
  }

  #tick() {
    if (this.#isStopped || this.#isAdPlaying || !this.#pump) return;
    this.#resumeWhenRateLimitPassed();
    if (this.#isStopped) return;
    const positionMs = this.#getPositionMs();
    this.#render(positionMs);
    if (this.#pump.stopReason !== null) return;
    // On pause the reserve is topped up once; after that no request is sent until playback moves on.
    // Deliberate second guard: chooseNextBatch already sends nothing once the reserve is met.
    if (this.#isPaused() && this.#track.translatedAheadMs(positionMs) >= this.#schedule.reserveAheadMs) return;
    this.#pump.tick().catch(() => {});
  }

  #render(positionMs) {
    const display = this.#track.displayAt(positionMs);
    let key;
    let draw;
    if (display.kind === 'text') {
      key = `text:${display.text}`;
      draw = () => this.#overlayView.showCueText(display.text);
    } else if ((display.kind === 'waiting' || display.kind === 'failed') && this.#stopStatusText !== null) {
      const statusText = this.#stopStatusText;
      key = `status:${statusText}`;
      draw = () => this.#overlayView.showStatus(statusText);
    } else if (display.kind === 'waiting') {
      key = `status:${STATUS_TEXTS.translating}`;
      draw = () => this.#overlayView.showStatus(STATUS_TEXTS.translating);
    } else {
      key = 'clear';
      draw = () => this.#overlayView.clear();
    }
    if (key === this.#lastRenderedKey) return;
    this.#lastRenderedKey = key;
    draw();
  }

  /** Opens the translator on the first batch that needs it, so a fully cached video sends nothing. */
  async #translateCues(cues) {
    try {
      if (!this.#translator) this.#translator = await this.#createTranslator(this.#languageName);
      return await this.#translator.translateCues(cues);
    } catch (error) {
      if (error instanceof ChatRateLimitedError) this.#rateLimitedUntilMs = error.retryAtMs;
      throw error;
    }
  }

  #handlePumpStopped(reason) {
    if (this.#isStopped) return;
    let statusText;
    let canRetry = false;
    if (reason === 'rate-limited') {
      statusText = rateLimitedText(this.#minutesUntilRateLimitEnds());
      canRetry = true;
    } else {
      statusText = STATUS_TEXT_BY_STOP_REASON[reason] ?? STATUS_TEXTS.repeatedFailures;
    }
    this.#reportStopStatus(statusText, canRetry);
  }

  #reportStopStatus(statusText, canRetry) {
    this.#stopStatusText = statusText;
    this.#lastRenderedKey = null;
    this.#onStatusChanged(statusText, { canRetry });
  }

  #minutesUntilRateLimitEnds() {
    const remainingMs = (this.#rateLimitedUntilMs ?? this.#now()) - this.#now();
    return Math.max(1, Math.ceil(remainingMs / MS_PER_MINUTE));
  }

  /** Keeps the minutes of the rate-limit text current and resumes once the limit has passed. */
  #resumeWhenRateLimitPassed() {
    if (this.#pump.stopReason !== 'rate-limited') return;
    if (this.#rateLimitedUntilMs !== null && this.#now() >= this.#rateLimitedUntilMs) {
      // By design the auto-resume also re-sends cues that failed earlier, as the manual retry does.
      this.retry();
      return;
    }
    const statusText = rateLimitedText(this.#minutesUntilRateLimitEnds());
    if (statusText !== this.#stopStatusText) this.#reportStopStatus(statusText, true);
  }

  async #loadCachedEntry() {
    try {
      return await this.#cache.load(this.#cacheKey);
    } catch {
      return null;
    }
  }

  /** Saves every translation of the track as one entry {translations: {<cueId>: string}}. */
  #saveTranslations() {
    if (this.#isStopped) return;
    const translations = this.#track.translationsByCueId();
    if (Object.keys(translations).length === 0) return;
    try {
      Promise.resolve(this.#cache.save(this.#cacheKey, { translations })).catch(() => {});
    } catch {
      // The cache is an optimisation only.
    }
  }
}
