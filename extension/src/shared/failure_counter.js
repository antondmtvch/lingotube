import {
  ChatRateLimitedError,
  ChatUnavailableError,
  NotSignedInError,
} from './chat_errors.js';

/** @typedef {'rate-limited'|'not-signed-in'|'chat-unavailable'|'repeated-failures'} ChatStopReason */

/** Failed chat messages in a row after which requests stop until the user retries. */
export const FAILED_MESSAGES_IN_A_ROW_LIMIT = 3;

/**
 * The stop reason of a chat error that ends requests at once; null for an error that only
 * counts as one failed message (ChatRequestFailedError and anything unexpected).
 * @param {unknown} error
 * @returns {Exclude<ChatStopReason, 'repeated-failures'>|null}
 */
export function stopReasonOfChatError(error) {
  if (error instanceof ChatRateLimitedError) return 'rate-limited';
  if (error instanceof NotSignedInError) return 'not-signed-in';
  if (error instanceof ChatUnavailableError) return 'chat-unavailable';
  return null;
}

/** Counts failed chat messages in a row; shared by the translation and the transcript pumps. */
export class FailureCounter {
  #limit;
  #failedInARow = 0;

  constructor(limit = FAILED_MESSAGES_IN_A_ROW_LIMIT) {
    this.#limit = limit;
  }

  /** A message that gave a usable result starts the count again. */
  recordSuccess() {
    this.#failedInARow = 0;
  }

  /** @returns {boolean} true when this failure reaches the limit */
  recordFailure() {
    this.#failedInARow += 1;
    return this.#failedInARow >= this.#limit;
  }

  reset() {
    this.#failedInARow = 0;
  }
}
