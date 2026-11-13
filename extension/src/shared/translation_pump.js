import {
  ChatRateLimitedError,
  ChatUnavailableError,
  NotSignedInError,
} from './chat_errors.js';
import { DEFAULT_SCHEDULE, chooseNextBatch } from './translation_schedule.js';

/** @typedef {'rate-limited'|'not-signed-in'|'chat-unavailable'|'repeated-failures'} PumpStopReason */

const FAILED_MESSAGES_IN_A_ROW_LIMIT = 3;

/**
 * Translates cues ahead of playback, one chat request at a time. The owner calls tick()
 * on its own timer; the pump has no timers, DOM or network of its own.
 */
export class TranslationPump {
  #track;
  #translator;
  #getPositionMs;
  #schedule;
  #onTranslationsChanged;
  #onStopped;
  #isStopped = false;
  #isEndedByOwner = false;
  #stopReason = null;
  #isRequestInFlight = false;
  #failedMessagesInARow = 0;

  /**
   * @param {{
   *   track: import('./cue_track.js').CueTrack,
   *   translator: {translateCues: (cues: object[]) => Promise<{translationsByCueId: Map<number,string>, failedCueIds: number[]}>},
   *   getPositionMs: () => number,
   *   schedule?: {reserveAheadMs: number, batchSize: number},
   *   onTranslationsChanged: () => void,
   *   onStopped: (reason: PumpStopReason) => void,
   * }} options
   */
  constructor({ track, translator, getPositionMs, schedule = DEFAULT_SCHEDULE, onTranslationsChanged, onStopped }) {
    this.#track = track;
    this.#translator = translator;
    this.#getPositionMs = getPositionMs;
    this.#schedule = schedule;
    this.#onTranslationsChanged = onTranslationsChanged;
    this.#onStopped = onStopped;
  }

  /** @returns {PumpStopReason|null} why the pump stopped by itself; null when running or stopped by the owner */
  get stopReason() {
    return this.#stopReason;
  }

  /** Ends the session: results of an in-flight request are discarded and no callback is called. */
  stop() {
    this.#isStopped = true;
    this.#isEndedByOwner = true;
  }

  /**
   * Starts working again after a stop caused by an error reason (the "retry" action).
   * Does nothing after stop() called by the owner.
   */
  resume() {
    if (this.#isEndedByOwner || this.#stopReason === null) return;
    this.#stopReason = null;
    this.#isStopped = false;
    this.#failedMessagesInARow = 0;
  }

  /** Sends the next batch when the translated reserve is short; does nothing when stopped or busy. */
  async tick() {
    if (this.#isStopped || this.#isRequestInFlight) return;
    const batch = chooseNextBatch(this.#track, this.#getPositionMs(), this.#schedule);
    if (batch.length === 0) return;

    this.#track.markPending(batch.map((cue) => cue.id));
    this.#isRequestInFlight = true;
    let result;
    try {
      result = await this.#translator.translateCues(batch);
    } catch (error) {
      this.#isRequestInFlight = false;
      if (this.#isStopped) return;
      this.#track.resetPending();
      this.#handleError(error);
      return;
    }
    this.#isRequestInFlight = false;
    if (this.#isStopped) return;
    this.#applyResult(result);
  }

  #applyResult({ translationsByCueId, failedCueIds }) {
    for (const [cueId, text] of translationsByCueId) this.#track.setTranslation(cueId, text);
    this.#track.markFailed(failedCueIds);
    if (translationsByCueId.size > 0) this.#failedMessagesInARow = 0;
    else this.#countFailedMessage();
    this.#onTranslationsChanged();
  }

  #handleError(error) {
    if (error instanceof ChatRateLimitedError) this.#stopWithReason('rate-limited');
    else if (error instanceof NotSignedInError) this.#stopWithReason('not-signed-in');
    else if (error instanceof ChatUnavailableError) this.#stopWithReason('chat-unavailable');
    else this.#countFailedMessage(); // ChatRequestFailedError and anything unexpected
  }

  #countFailedMessage() {
    this.#failedMessagesInARow += 1;
    if (this.#failedMessagesInARow >= FAILED_MESSAGES_IN_A_ROW_LIMIT) this.#stopWithReason('repeated-failures');
  }

  #stopWithReason(reason) {
    this.#isStopped = true;
    this.#stopReason = reason;
    this.#onStopped(reason);
  }
}
