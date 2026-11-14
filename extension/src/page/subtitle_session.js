import { NoCaptionTracksError } from './youtube_captions_source.js';
import { CHAT_TRANSCRIPT_SOURCE_KEY, translationCacheKey } from '../shared/cache_key.js';
import { ChatRateLimitedError } from '../shared/chat_errors.js';
import { CueTrack } from '../shared/cue_track.js';
import { promptLanguageName } from '../shared/language_choices.js';
import { uiTexts } from '../shared/ui_strings.js';
import { decideWaitAction } from '../shared/subtitle_wait.js';
import { TranscriptChunkPump } from '../shared/transcript_chunk_pump.js';
import { TranscriptChunkStore } from '../shared/transcript_chunks.js';
import { TranslationPump } from '../shared/translation_pump.js';
import { DEFAULT_SCHEDULE } from '../shared/translation_schedule.js';

/** @typedef {import('../shared/sentence_cues.js').Cue} Cue */

const TICK_INTERVAL_MS = 250;
const MS_PER_MINUTE = 60000;
// A position step backwards, or forward by more than twice the real time since the previous
// tick plus this slack, is a seek, not playback (even a stalled tab moves the position by about
// the elapsed time).
const SEEK_SLACK_MS = 2000;
// The browser may round currentTime back a little on pause() or play(); that is not a seek.
const SEEK_BACK_TOLERANCE_MS = 500;

/**
 * Translated subtitles of ONE video in ONE language: loads the cues, restores cached
 * translations, and on a 250 ms timer shows the cue under the playhead and lets the pump
 * translate ahead. Without usable YouTube captions it falls back to a translated transcript
 * from the chat, in chunks, with the "approximate timing" label. A new video or language gets
 * a new session; after stop() nothing of this session reaches the view, the status callback
 * or the cache.
 */
export class SubtitleSession {
  #videoId;
  #language;
  #languageName;
  #loadCues;
  #createTranslator;
  #createTranscriptSource;
  #getDurationMs;
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
  #pauseVideo;
  #playVideo;
  #isWaitForSubtitlesEnabled;
  #texts;
  #statusTextByStopReason;

  #isStarted = false;
  #isStopped = false;
  #isAdPlaying = false;
  #timerHandle = null;
  /** Caption mode: the cues and their translations. */
  #track = null;
  /** Fallback mode: the chat transcript chunks. */
  #chunkStore = null;
  /** What the box shows: the track or the chunk store (both answer displayAt and resetFailed). */
  #display = null;
  /** The TranslationPump or the TranscriptChunkPump. */
  #pump = null;
  #cacheKey = null;
  #translator = null;
  #transcriptSource = null;
  /** The panel says "captions not fetched" until the first chunk is shown. */
  #isCaptionsNotFetchedShown = false;
  #rateLimitedUntilMs = null;
  /** Shown in the box instead of "Перевожу…" while the pump is stopped by an error. */
  #stopStatusText = null;
  #lastRenderedKey = null;
  /** We paused the video to wait for a translation and the pause is still ours. */
  #pausedByUs = false;
  /** When the current wait for a translation began; null while nothing is awaited. */
  #waitStartedMs = null;
  /** The wait cap expired for the current wait: the video plays on and the box says so. */
  #isWaitCapped = false;
  /** The panel currently shows "translation delayed" because of the cap. */
  #isDelayedStatusReported = false;
  /** The user pressed play over our pause: this wait sets no new pause. */
  #isWaitDismissedByUser = false;
  #lastTickPositionMs = null;
  #lastTickNowMs = null;

  /**
   * @param {{
   *   videoId: string,
   *   language: import('../shared/language_choices.js').TargetLanguage,
   *   loadCues: () => Promise<{cues: Cue[], sourceKey: string}>,
   *   createTranslator: (languageName: string) => Promise<{translateCues: Function}>,
   *   createTranscriptSource: (languageName: string, durationMs: number) => Promise<{requestChunk: Function}>,
   *   getDurationMs: () => number,
   *   cache: {load: (key: string) => Promise<object|null>, save: (key: string, entry: object) => Promise<void>},
   *   overlayView: {showCueText: Function, showStatus: Function, clear: Function, setHidden: Function,
   *     setApproximateTimingLabel: Function},
   *   getPositionMs: () => number,
   *   isPaused?: () => boolean,
   *   setTimer: (callback: () => void, intervalMs: number) => any,
   *   clearTimer: (handle: any) => void,
   *   onStatusChanged: (statusText: string|null, details: {canRetry: boolean}) => void,
   *   logInfo?: (message: string, details: object) => void,
   *   now?: () => number,
   *   schedule?: {reserveAheadMs: number, batchSize: number},
   *   pauseVideo?: () => void,
   *   playVideo?: () => void,
   *   isWaitForSubtitlesEnabled?: () => boolean,
   *   texts?: Record<string, any>,
   * }} options
   */
  constructor({
    videoId,
    language,
    loadCues,
    createTranslator,
    createTranscriptSource,
    getDurationMs,
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
    pauseVideo = () => {},
    playVideo = () => {},
    isWaitForSubtitlesEnabled = () => false,
    texts = uiTexts('ru'),
  }) {
    this.#videoId = videoId;
    this.#language = language;
    this.#languageName = promptLanguageName(language);
    this.#loadCues = loadCues;
    this.#createTranslator = createTranslator;
    this.#createTranscriptSource = createTranscriptSource;
    this.#getDurationMs = getDurationMs;
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
    this.#pauseVideo = pauseVideo;
    this.#playVideo = playVideo;
    this.#isWaitForSubtitlesEnabled = isWaitForSubtitlesEnabled;
    this.#texts = texts;
    this.#statusTextByStopReason = {
      'not-signed-in': texts.notSignedIn,
      'chat-unavailable': texts.chatUnavailable,
      'repeated-failures': texts.repeatedFailures,
      'no-speech': texts.noSpeech,
    };
  }

  /** Loads the cues and cached translations, then starts the timer. Never rejects. */
  async start() {
    if (this.#isStarted || this.#isStopped) return;
    this.#isStarted = true;
    if (!this.#isAdPlaying) this.#overlayView.showStatus(this.#texts.translating);

    let loaded = null;
    let hasCaptionTracks = true;
    try {
      loaded = await this.#loadCues();
    } catch (error) {
      loaded = null;
      hasCaptionTracks = !(error instanceof NoCaptionTracksError);
      // Error texts of the caption loaders never carry the URL or the pot token.
      this.#logInfo('lingotube: YouTube captions not used', {
        reason: error?.name ?? typeof error,
        message: String(error?.message ?? error),
      });
    }
    if (this.#isStopped) return;
    if (!loaded || !Array.isArray(loaded.cues) || loaded.cues.length === 0) {
      if (loaded) this.#logInfo('lingotube: YouTube captions not used', { reason: 'no cues' });
      await this.#startTranscriptFallback({ hasCaptionTracks });
      return;
    }
    await this.#startCaptionMode(loaded);
  }

  async #startCaptionMode(loaded) {
    this.#track = new CueTrack(loaded.cues);
    this.#display = this.#track;
    this.#cacheKey = translationCacheKey({
      videoId: this.#videoId,
      language: this.#language,
      sourceKey: loaded.sourceKey,
    });
    const cachedEntry = await this.#loadCachedEntry();
    if (this.#isStopped) return;
    if (cachedEntry?.translations) this.#track.loadTranslations(cachedEntry.translations);

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
    this.#startTimer();
  }

  /**
   * The fallback without usable captions: a translated transcript from the chat, in chunks.
   * The approximate-timing label is always on; when a track existed but its text could not be
   * fetched, the panel says so until the first chunk is shown.
   */
  async #startTranscriptFallback({ hasCaptionTracks }) {
    const rawDurationMs = Number(this.#getDurationMs());
    // Infinity is a live stream: it has no end, so the transcript cannot be chunked.
    const durationMs = Number.isFinite(rawDurationMs) && rawDurationMs > 0 ? rawDurationMs : 0;
    if (durationMs <= 0) {
      this.#overlayView.clear();
      this.#onStatusChanged(this.#texts.captionsNotFetched, { canRetry: false });
      return;
    }
    this.#overlayView.setApproximateTimingLabel(true);
    if (hasCaptionTracks) {
      this.#isCaptionsNotFetchedShown = true;
      this.#onStatusChanged(this.#texts.captionsNotFetched, { canRetry: false });
    }

    this.#chunkStore = new TranscriptChunkStore(durationMs);
    this.#display = this.#chunkStore;
    this.#cacheKey = translationCacheKey({
      videoId: this.#videoId,
      language: this.#language,
      sourceKey: CHAT_TRANSCRIPT_SOURCE_KEY,
    });
    const cachedEntry = await this.#loadCachedEntry();
    if (this.#isStopped) return;
    const cachedChunks = cachedEntry ? this.#chunkStore.loadCacheEntry(cachedEntry) : 0;

    this.#pump = new TranscriptChunkPump({
      store: this.#chunkStore,
      source: { requestChunk: (index) => this.#requestChunk(index, durationMs) },
      getPositionMs: this.#getPositionMs,
      reserveAheadMs: this.#schedule.reserveAheadMs,
      onChunksChanged: () => this.#saveChunks(),
      onStopped: (reason) => this.#handlePumpStopped(reason),
    });
    this.#logInfo('lingotube: transcript fallback started', {
      chunks: this.#chunkStore.chunkCount,
      cachedChunks,
    });
    this.#startTimer();
  }

  #startTimer() {
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
    this.#releaseOurPause();
  }

  /** The "retry" action: resumes a pump stopped by an error and re-schedules failed cues or chunks. */
  retry() {
    if (this.#isStopped || !this.#pump) return;
    this.#pump.resume();
    this.#display.resetFailed();
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
    if (isAdPlaying) {
      this.#releaseOurPause();
      this.#resetWait();
      this.#overlayView.clear();
    }
    this.#overlayView.setHidden(isAdPlaying);
  }

  #tick() {
    if (this.#isStopped || this.#isAdPlaying || !this.#pump) return;
    this.#resumeWhenRateLimitPassed();
    if (this.#isStopped) return;
    const positionMs = this.#getPositionMs();
    const isWaiting = this.#render(positionMs);
    this.#applyWaitDecision(positionMs, isWaiting);
    if (this.#pump.stopReason !== null) return;
    // On pause the reserve is topped up once; after that no request is sent until playback moves on.
    // Deliberate second guard: chooseNextBatch already sends nothing once the reserve is met.
    // In the fallback the chunk choice alone guards it: no chunk is due once the reserve is met.
    if (
      this.#track
      && this.#isPaused()
      && this.#track.translatedAheadMs(positionMs) >= this.#schedule.reserveAheadMs
    ) return;
    this.#pump.tick().catch(() => {});
  }

  /**
   * Pauses the video while the cue under the playhead is being translated and resumes it once
   * the cue is ready, an ad starts, the setting is switched off or the wait cap is reached.
   * A pause the user made is never touched: only a pause we made (#pausedByUs) is released.
   */
  #applyWaitDecision(positionMs, isWaiting) {
    const nowMs = this.#now();
    this.#restartWaitOnSeek(positionMs, isWaiting, nowMs);
    if (isWaiting && this.#waitStartedMs === null) this.#waitStartedMs = nowMs;

    const durationMs = Number(this.#getDurationMs());
    const isVideoPaused = this.#isPaused();
    if (isWaiting && this.#pausedByUs && !isVideoPaused) this.#isWaitDismissedByUser = true;
    if (!isWaiting) this.#isWaitDismissedByUser = false;
    const decision = decideWaitAction({
      isEnabled: this.#isWaitForSubtitlesEnabled(),
      isWaiting,
      isAdPlaying: this.#isAdPlaying,
      isPumpStopped: this.#pump.stopReason !== null,
      isAtVideoEnd: Number.isFinite(durationMs) && durationMs > 0 && positionMs >= durationMs,
      isVideoPaused,
      pausedByUs: this.#pausedByUs,
      waitStartedMs: this.#waitStartedMs,
      isCapped: this.#isWaitCapped,
      isDismissedByUser: this.#isWaitDismissedByUser,
      nowMs,
    });
    this.#pausedByUs = decision.pausedByUs;
    if (decision.action === 'pause') {
      this.#callVideo(this.#pauseVideo, 'pause', { onFailure: () => { this.#pausedByUs = false; } });
    } else if (decision.action === 'play') {
      this.#callVideo(this.#playVideo, 'play');
    }
    if (!isWaiting) this.#waitStartedMs = null;
    this.#updateCapState(decision.isCapped);
  }

  /** A seek during a wait starts a new wait on the new position, with a fresh 30 s. */
  #restartWaitOnSeek(positionMs, isWaiting, nowMs) {
    const previousPositionMs = this.#lastTickPositionMs;
    const previousNowMs = this.#lastTickNowMs;
    this.#lastTickPositionMs = positionMs;
    this.#lastTickNowMs = nowMs;
    if (!isWaiting || previousPositionMs === null || previousNowMs === null) return;
    const stepMs = positionMs - previousPositionMs;
    const elapsedMs = Math.max(0, nowMs - previousNowMs);
    if (stepMs < -SEEK_BACK_TOLERANCE_MS || stepMs > elapsedMs * 2 + SEEK_SLACK_MS) {
      this.#waitStartedMs = nowMs;
      this.#isWaitCapped = false;
      this.#isWaitDismissedByUser = false;
    }
  }

  /** Mirrors the cap flag into the box and the panel; the box is redrawn when it changes. */
  #updateCapState(isCapped) {
    if (isCapped === this.#isWaitCapped && isCapped === this.#isDelayedStatusReported) return;
    this.#isWaitCapped = isCapped;
    this.#lastRenderedKey = null;
    this.#render(this.#getPositionMs());
    if (isCapped && this.#stopStatusText === null && !this.#isDelayedStatusReported) {
      this.#isDelayedStatusReported = true;
      this.#onStatusChanged(this.#texts.translationDelayed, { canRetry: false });
    } else if (!isCapped && this.#isDelayedStatusReported) {
      this.#isDelayedStatusReported = false;
      if (this.#stopStatusText === null) this.#onStatusChanged(null, { canRetry: false });
    }
  }

  /** Calls the video callback; its failure never reaches the tick. */
  #callVideo(callback, name, { onFailure = () => {} } = {}) {
    try {
      callback();
    } catch {
      onFailure();
      this.#logInfo(`lingotube: video ${name} failed`, {});
    }
  }

  /** Gives back the video if we are holding it and it is still paused. */
  #releaseOurPause() {
    if (!this.#pausedByUs) return;
    this.#pausedByUs = false;
    if (this.#isPaused()) this.#callVideo(this.#playVideo, 'play');
  }

  #resetWait() {
    this.#waitStartedMs = null;
    this.#isWaitCapped = false;
    this.#isWaitDismissedByUser = false;
    this.#lastTickPositionMs = null;
    this.#lastTickNowMs = null;
    if (this.#isDelayedStatusReported) {
      this.#isDelayedStatusReported = false;
      if (this.#stopStatusText === null) this.#onStatusChanged(null, { canRetry: false });
    }
  }

  /** @returns {boolean} whether the box shows "translating" for the cue under the playhead */
  #render(positionMs) {
    const display = this.#display.displayAt(positionMs);
    if (display.kind === 'text') this.#endCaptionsNotFetchedStatus();
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
      const statusText = this.#isWaitCapped ? this.#texts.translationDelayed : this.#texts.translating;
      key = `status:${statusText}`;
      draw = () => this.#overlayView.showStatus(statusText);
    } else {
      key = 'clear';
      draw = () => this.#overlayView.clear();
    }
    const isWaiting = display.kind === 'waiting' && this.#stopStatusText === null;
    if (key === this.#lastRenderedKey) return isWaiting;
    this.#lastRenderedKey = key;
    draw();
    return isWaiting;
  }

  /** The first shown chunk takes over from the "captions not fetched" line of the panel. */
  #endCaptionsNotFetchedStatus() {
    if (!this.#isCaptionsNotFetchedShown) return;
    this.#isCaptionsNotFetchedShown = false;
    if (this.#stopStatusText === null) this.#onStatusChanged(null, { canRetry: false });
  }

  /** Opens the translator on the first batch that needs it, so a fully cached video sends nothing. */
  async #translateCues(cues) {
    try {
      if (!this.#translator) this.#translator = await this.#createTranslator(this.#languageName);
      return await this.#translator.translateCues(cues);
    } catch (error) {
      this.#rememberRateLimit(error);
      throw error;
    }
  }

  /** Opens the transcript source on the first chunk that needs it, as #translateCues does. */
  async #requestChunk(index, durationMs) {
    try {
      if (!this.#transcriptSource) {
        this.#transcriptSource = await this.#createTranscriptSource(this.#languageName, durationMs);
      }
      return await this.#transcriptSource.requestChunk(index);
    } catch (error) {
      this.#rememberRateLimit(error);
      throw error;
    }
  }

  #rememberRateLimit(error) {
    if (error instanceof ChatRateLimitedError) this.#rateLimitedUntilMs = error.retryAtMs;
  }

  #handlePumpStopped(reason) {
    if (this.#isStopped) return;
    let statusText;
    let canRetry = false;
    if (reason === 'rate-limited') {
      statusText = this.#texts.rateLimited(this.#minutesUntilRateLimitEnds());
      canRetry = true;
    } else {
      statusText = this.#statusTextByStopReason[reason] ?? this.#texts.repeatedFailures;
    }
    this.#reportStopStatus(statusText, canRetry);
  }

  #reportStopStatus(statusText, canRetry) {
    this.#isCaptionsNotFetchedShown = false;
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
    const statusText = this.#texts.rateLimited(this.#minutesUntilRateLimitEnds());
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

  /** Saves every loaded chunk as one entry {chunks: {<index>: [{startMs, endMs, text}]}}. */
  #saveChunks() {
    if (this.#isStopped) return;
    const entry = this.#chunkStore.toCacheEntry();
    if (Object.keys(entry.chunks).length === 0) return;
    try {
      Promise.resolve(this.#cache.save(this.#cacheKey, entry)).catch(() => {});
    } catch {
      // The cache is an optimisation only.
    }
  }
}
