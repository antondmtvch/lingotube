// Errors of the Ask chat. Messages are fixed English text: never put request data
// (URL, headers, tokens, response bodies) into them.

/** The video has no Ask chat (no panel or no send command). */
export class ChatUnavailableError extends Error {
  constructor() {
    super('The YouTube Ask chat is not available for this video.');
    this.name = 'ChatUnavailableError';
  }
}

/** YouTube does not see a signed-in account. */
export class NotSignedInError extends Error {
  constructor() {
    super('YouTube does not see a signed-in account.');
    this.name = 'NotSignedInError';
  }
}

/** YouTube answered HTTP 429; no chat request should be sent before `retryAtMs`. */
export class ChatRateLimitedError extends Error {
  /** @param {number} retryAtMs epoch milliseconds when requests may resume */
  constructor(retryAtMs) {
    super('YouTube is rate limiting the chat.');
    this.name = 'ChatRateLimitedError';
    this.retryAtMs = retryAtMs;
  }
}

/** The chat request failed and retrying did not help (or is pointless). */
export class ChatRequestFailedError extends Error {
  constructor() {
    super('The YouTube chat request failed.');
    this.name = 'ChatRequestFailedError';
  }
}
