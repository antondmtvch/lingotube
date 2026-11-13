// Paces Ask chat requests across ALL tabs of the browser: one request at a time, at least
// MIN_GAP_BETWEEN_STARTS_MS between starts, nothing from a hidden tab, and a shared cooldown
// after HTTP 429. Only two timestamps are stored; tokens never reach storage.

import { ChatRateLimitedError } from '../shared/chat_errors.js';

const LOCK_NAME = 'lingotube-chat-request';
const LAST_START_KEY = 'lingotube:lastChatRequestStartedAtMs';
const COOLDOWN_UNTIL_KEY = 'lingotube:chatCooldownUntilMs';
const MIN_GAP_BETWEEN_STARTS_MS = 5000;
const COOLDOWN_DURATION_MS = 600000;

export class ChatRequestGate {
  /**
   * @param {object} dependencies
   * @param {{request: (name: string, callback: () => Promise<any>) => Promise<any>}} dependencies.lockManager navigator.locks shape
   * @param {{getItem: Function, setItem: Function, removeItem: Function}} dependencies.keyValueStorage localStorage shape; may throw
   * @param {() => boolean} dependencies.isTabVisible
   * @param {() => Promise<void>} dependencies.waitUntilTabVisible resolves on the next change to visible
   * @param {() => number} dependencies.now epoch milliseconds
   * @param {(ms: number) => Promise<void>} dependencies.sleep
   */
  constructor({ lockManager, keyValueStorage, isTabVisible, waitUntilTabVisible, now, sleep }) {
    this.lockManager = lockManager;
    this.keyValueStorage = keyValueStorage;
    this.isTabVisible = isTabVisible;
    this.waitUntilTabVisible = waitUntilTabVisible;
    this.now = now;
    this.sleep = sleep;
    this.lastStartInThisTabMs = null;
  }

  /**
   * Runs `sendRequest` when the tab is visible, no cooldown is active and the gap since the
   * previous start (in any tab) has passed. Returns or rethrows whatever `sendRequest` does.
   * @template T
   * @param {() => Promise<T>} sendRequest
   * @returns {Promise<T>}
   */
  async run(sendRequest) {
    while (!this.isTabVisible()) {
      await this.waitUntilTabVisible();
    }
    this.#throwIfCoolingDown();
    return this.lockManager.request(LOCK_NAME, async () => {
      // A cooldown may have started in another tab while this request waited in the queue.
      this.#throwIfCoolingDown();
      const waitMs = this.#lastStartMs() + MIN_GAP_BETWEEN_STARTS_MS - this.now();
      if (waitMs > 0) {
        await this.sleep(waitMs);
      }
      const startedAtMs = this.now();
      this.lastStartInThisTabMs = startedAtMs;
      this.#writeNumber(LAST_START_KEY, startedAtMs);
      return sendRequest();
    });
  }

  /** Stops all chat requests from every tab for 10 minutes. */
  startCooldown() {
    this.#writeNumber(COOLDOWN_UNTIL_KEY, this.now() + COOLDOWN_DURATION_MS);
  }

  /** @returns {number} milliseconds left of the cooldown, 0 when none */
  cooldownRemainingMs() {
    const untilMs = this.#readNumber(COOLDOWN_UNTIL_KEY);
    return untilMs === null ? 0 : Math.max(0, untilMs - this.now());
  }

  /** Ends the cooldown early (the manual retry button). */
  clearCooldown() {
    try {
      this.keyValueStorage.removeItem(COOLDOWN_UNTIL_KEY);
    } catch {
      // Storage unavailable: nothing to clear.
    }
  }

  #throwIfCoolingDown() {
    const remainingMs = this.cooldownRemainingMs();
    if (remainingMs > 0) {
      throw new ChatRateLimitedError(this.now() + remainingMs);
    }
  }

  /** Latest known start of a chat request, from storage or this tab; -Infinity when unknown. */
  #lastStartMs() {
    const stored = this.#readNumber(LAST_START_KEY);
    return Math.max(stored ?? -Infinity, this.lastStartInThisTabMs ?? -Infinity);
  }

  #readNumber(key) {
    try {
      const text = this.keyValueStorage.getItem(key);
      if (text === null || text === undefined || text === '') return null;
      const value = Number(text);
      return Number.isFinite(value) ? value : null;
    } catch {
      return null;
    }
  }

  #writeNumber(key, value) {
    try {
      this.keyValueStorage.setItem(key, String(value));
    } catch {
      // Storage unavailable: pacing falls back to this tab's memory.
    }
  }
}
