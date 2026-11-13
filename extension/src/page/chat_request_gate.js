// Paces Ask chat requests across ALL tabs of the browser: one request at a time, at least
// MIN_GAP_BETWEEN_STARTS_MS between starts, nothing from a hidden tab, and a shared cooldown
// after HTTP 429. Only two timestamps are stored; tokens never reach storage.

import { ChatRateLimitedError } from '../shared/chat_errors.js';

const LOCK_NAME = 'lingotube-chat-request';
const LAST_START_KEY = 'lingotube:lastChatRequestStartedAtMs';
const COOLDOWN_UNTIL_KEY = 'lingotube:chatCooldownUntilMs';
const MIN_GAP_BETWEEN_STARTS_MS = 5000;
const COOLDOWN_DURATION_MS = 600000;
const RETRY_OUTSIDE_LOCK = Symbol('retry outside lock');

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
    this.cooldownUntilInThisTabMs = null;
  }

  /**
   * Runs `sendRequest` when the tab is visible, no cooldown is active and the gap since the
   * previous start (in any tab) has passed. Returns or rethrows whatever `sendRequest` does.
   * @template T
   * @param {() => Promise<T>} sendRequest
   * @returns {Promise<T>}
   */
  async run(sendRequest) {
    for (;;) {
      while (!this.isTabVisible()) {
        await this.waitUntilTabVisible();
      }
      this.#throwIfCoolingDown();
      const outcome = await this.lockManager.request(LOCK_NAME, async () => {
        // A cooldown may have started in another tab while this request waited in the queue.
        this.#throwIfCoolingDown();
        // Clamp: a future last start (clock moved back, garbage value) must not hold the lock long.
        const waitMs = Math.min(
          this.#lastStartMs() + MIN_GAP_BETWEEN_STARTS_MS - this.now(),
          MIN_GAP_BETWEEN_STARTS_MS,
        );
        if (waitMs > 0) {
          await this.sleep(waitMs);
        }
        // The tab may have been hidden, or another tab hit a 429, during the wait. Never wait
        // for visibility inside the lock (it would block other tabs): leave and retry outside.
        if (!this.isTabVisible() || this.cooldownRemainingMs() > 0) {
          return RETRY_OUTSIDE_LOCK;
        }
        const startedAtMs = this.now();
        this.lastStartInThisTabMs = startedAtMs;
        this.#writeNumber(LAST_START_KEY, startedAtMs);
        return { result: await sendRequest() };
      });
      if (outcome === RETRY_OUTSIDE_LOCK) {
        this.#throwIfCoolingDown();
        continue;
      }
      return outcome.result;
    }
  }

  /** Stops all chat requests from every tab for 10 minutes. */
  startCooldown() {
    const untilMs = this.now() + COOLDOWN_DURATION_MS;
    // Kept in memory only when storage refused the write; otherwise storage is the single truth,
    // so a manual clear in another tab is honoured here too.
    this.cooldownUntilInThisTabMs = this.#writeNumber(COOLDOWN_UNTIL_KEY, untilMs) ? null : untilMs;
  }

  /** @returns {number} milliseconds left of the cooldown, 0 when none */
  cooldownRemainingMs() {
    const untilMs = Math.max(
      this.#readNumber(COOLDOWN_UNTIL_KEY) ?? -Infinity,
      this.cooldownUntilInThisTabMs ?? -Infinity,
    );
    // Capped: a far-future value (clock moved back, garbage) must not lock requests out for long.
    return Math.min(COOLDOWN_DURATION_MS, Math.max(0, untilMs - this.now()));
  }

  /** Ends the cooldown early (the manual retry button). */
  clearCooldown() {
    this.cooldownUntilInThisTabMs = null;
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
      return true;
    } catch {
      // Storage unavailable: pacing falls back to this tab's memory.
      return false;
    }
  }
}
