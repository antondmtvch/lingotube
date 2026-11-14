import { FailureCounter, stopReasonOfChatError } from './failure_counter.js';
import { TRANSCRIPT_RESERVE_AHEAD_MS } from './transcript_chunks.js';

/** @typedef {import('./failure_counter.js').ChatStopReason|'no-speech'} TranscriptPumpStopReason */

/**
 * Requests chat transcript chunks around the playhead, one request at a time, with the
 * failure rules of the translation pump: three failed messages in a row stop it, and the chat
 * errors map to the same stop reasons. A chunk that comes back with no lines is failed and
 * counts as a failed message; when every chunk of the video failed the stop reason is
 * 'no-speech'. A thrown request failure leaves the chunk missing, so it is asked again.
 * The owner calls tick() on its own timer.
 */
export class TranscriptChunkPump {
  #store;
  #source;
  #getPositionMs;
  #reserveAheadMs;
  #onChunksChanged;
  #onStopped;
  #isStopped = false;
  #isEndedByOwner = false;
  #stopReason = null;
  #isRequestInFlight = false;
  #failedMessages = new FailureCounter();

  /**
   * @param {{
   *   store: import('./transcript_chunks.js').TranscriptChunkStore,
   *   source: {requestChunk: (index: number) => Promise<import('./timestamped_transcript.js').TimedLine[]>},
   *   getPositionMs: () => number,
   *   reserveAheadMs?: number,
   *   onChunksChanged: () => void,
   *   onStopped: (reason: TranscriptPumpStopReason) => void,
   * }} options
   */
  constructor({
    store,
    source,
    getPositionMs,
    reserveAheadMs = TRANSCRIPT_RESERVE_AHEAD_MS,
    onChunksChanged,
    onStopped,
  }) {
    this.#store = store;
    this.#source = source;
    this.#getPositionMs = getPositionMs;
    this.#reserveAheadMs = reserveAheadMs;
    this.#onChunksChanged = onChunksChanged;
    this.#onStopped = onStopped;
  }

  /** @returns {TranscriptPumpStopReason|null} why the pump stopped by itself; null when running or stopped by the owner */
  get stopReason() {
    return this.#stopReason;
  }

  /** Ends the session: the reply of an in-flight request is discarded and no callback is called. */
  stop() {
    this.#isStopped = true;
    this.#isEndedByOwner = true;
  }

  /** Starts working again after a stop caused by an error reason; nothing after stop(). */
  resume() {
    if (this.#isEndedByOwner || this.#stopReason === null) return;
    this.#stopReason = null;
    this.#isStopped = false;
    this.#failedMessages.reset();
  }

  /** Requests the next chunk the playhead needs; does nothing when stopped or busy. */
  async tick() {
    if (this.#isStopped || this.#isRequestInFlight) return;
    const index = this.#store.nextChunkToRequest(this.#getPositionMs(), this.#reserveAheadMs);
    if (index === null) return;

    this.#isRequestInFlight = true;
    let cues;
    try {
      cues = await this.#source.requestChunk(index);
    } catch (error) {
      this.#isRequestInFlight = false;
      if (this.#isStopped) return;
      const reason = stopReasonOfChatError(error);
      if (reason !== null) this.#stopWithReason(reason);
      else this.#countFailedMessage(); // ChatRequestFailedError and anything unexpected
      return;
    }
    this.#isRequestInFlight = false;
    if (this.#isStopped) return;
    if (!Array.isArray(cues) || cues.length === 0) {
      this.#store.markChunkFailed(index);
      this.#countFailedMessage();
      return;
    }
    this.#store.addChunk(index, cues);
    this.#failedMessages.recordSuccess();
    this.#onChunksChanged();
  }

  #countFailedMessage() {
    const isLimitReached = this.#failedMessages.recordFailure();
    if (this.#store.areAllChunksFailed()) this.#stopWithReason('no-speech');
    else if (isLimitReached) this.#stopWithReason('repeated-failures');
  }

  #stopWithReason(reason) {
    this.#isStopped = true;
    this.#stopReason = reason;
    this.#onStopped(reason);
  }
}
