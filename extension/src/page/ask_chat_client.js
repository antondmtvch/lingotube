// Client of YouTube's Ask chat, running inside the YouTube page (MAIN world).
// Port of src/lingotube/ask/client.py. Requests are same-origin relative URLs; everything
// environment-specific is injected so the module is testable without a browser.
// Tokens (SAPISID, the hash, chat continuation, visitorData) are never logged or put into errors.

import {
  findSendCommand,
  findChatPanelToken,
  isSignedIn,
  buildAskBody,
  extractAnswer,
} from '../shared/ask_chat_wire.js';
import {
  ChatUnavailableError,
  NotSignedInError,
  ChatRateLimitedError,
  ChatRequestFailedError,
} from '../shared/chat_errors.js';

const YOUTUBE_ORIGIN = 'https://www.youtube.com';
const REQUEST_TIMEOUT_MS = 60000;
const MAX_RETRIES = 2;

/**
 * @param {{cookieText: string, origin: string, nowSeconds: number, sha1Hex: (text: string) => Promise<string>}} params
 * @returns {Promise<string>} the Authorization header value
 */
export async function sapisidHashHeader({ cookieText, origin, nowSeconds, sha1Hex }) {
  const cookies = new Map();
  for (const pair of cookieText.split(';')) {
    const at = pair.indexOf('=');
    if (at > 0) cookies.set(pair.slice(0, at).trim(), pair.slice(at + 1).trim());
  }
  const sapisid = cookies.get('SAPISID') || cookies.get('__Secure-3PAPISID');
  if (!sapisid) throw new NotSignedInError();
  const digest = await sha1Hex(`${nowSeconds} ${sapisid} ${origin}`);
  return `SAPISIDHASH ${nowSeconds}_${digest}`;
}

/** Internal marker: this attempt failed in a way that is worth repeating. */
class RetryableFailure extends Error {}

/**
 * @typedef {object} Environment
 * @property {object} context innertube context (window.ytcfg.get('INNERTUBE_CONTEXT'))
 * @property {number} sessionIndex
 * @property {typeof fetch} fetch
 * @property {{run: Function, startCooldown: Function, cooldownRemainingMs: () => number}} gate
 * @property {string} cookieText
 * @property {() => number} now epoch milliseconds
 * @property {(text: string) => Promise<string>} sha1Hex
 */

/** One request attempt through the gate. Throws RetryableFailure or a final chat error. */
async function postOnce(environment, path, body) {
  const { context, sessionIndex, fetch, gate, cookieText, now, sha1Hex } = environment;
  const authorization = await sapisidHashHeader({
    cookieText,
    origin: YOUTUBE_ORIGIN,
    nowSeconds: Math.floor(now() / 1000),
    sha1Hex,
  });
  const headers = {
    'Content-Type': 'application/json',
    Authorization: authorization,
    'X-Origin': YOUTUBE_ORIGIN,
    'X-Goog-AuthUser': String(sessionIndex),
    'X-Youtube-Client-Name': '1',
  };
  if (typeof context?.client?.clientVersion === 'string') {
    headers['X-Youtube-Client-Version'] = context.client.clientVersion;
  }
  if (typeof context?.client?.visitorData === 'string') {
    headers['X-Goog-Visitor-Id'] = context.client.visitorData;
  }
  let response;
  try {
    response = await gate.run(() =>
      fetch(`/youtubei/v1/${path}?prettyPrint=false`, {
        method: 'POST',
        credentials: 'include',
        redirect: 'error',
        headers,
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      }),
    );
  } catch {
    throw new RetryableFailure();
  }
  const { status } = response;
  if (status === 401 || status === 403) throw new NotSignedInError();
  if (status === 429) {
    gate.startCooldown();
    throw new ChatRateLimitedError(now() + gate.cooldownRemainingMs());
  }
  if (status >= 500) throw new RetryableFailure();
  if (status < 200 || status >= 300) throw new ChatRequestFailedError();
  try {
    return await response.json();
  } catch {
    throw new RetryableFailure();
  }
}

/**
 * POST with up to MAX_RETRIES repeats of the same request on retryable failures.
 * @param {(data: object) => T} accept validates/derives the result; throw RetryableFailure to retry
 * @template T
 */
async function postWithRetries(environment, path, body, accept = (data) => data) {
  for (let attempt = 0; ; attempt++) {
    try {
      const data = await postOnce(environment, path, body());
      if (data === null || typeof data !== 'object') throw new RetryableFailure();
      return accept(data);
    } catch (error) {
      if (!(error instanceof RetryableFailure)) throw error;
      if (attempt >= MAX_RETRIES) throw new ChatRequestFailedError();
    }
  }
}

/** One Ask chat for one video. Remembers the current send command between questions. */
class AskChatSession {
  #environment;
  #command;

  constructor(environment, command) {
    this.#environment = environment;
    this.#command = command;
  }

  /**
   * @param {string} prompt
   * @returns {Promise<string>} the chat's answer
   */
  async ask(prompt) {
    const command = this.#command;
    const { answer, fresh } = await postWithRetries(
      this.#environment,
      'get_panel',
      () => buildAskBody({ context: this.#environment.context, command, prompt, nowMs: this.#environment.now() }),
      (data) => {
        const text = extractAnswer(data);
        if (!text) throw new RetryableFailure();
        return { answer: text, fresh: findSendCommand(data, { panelOnly: false }) };
      },
    );
    if (fresh !== null) this.#command = fresh;
    return answer;
  }
}

/**
 * Open the Ask chat of a video: `next` → send command (→ optional empty initial get_panel).
 * @param {Environment & {videoId: string}} params
 * @returns {Promise<AskChatSession>}
 */
export async function openAskChat({ videoId, ...environment }) {
  const { context } = environment;
  const next = await postWithRetries(environment, 'next', () => ({ context, videoId }));
  if (!isSignedIn(next)) throw new NotSignedInError();
  let command = findSendCommand(next);
  if (command === null) {
    const panelToken = findChatPanelToken(next);
    if (panelToken) {
      const initial = await postWithRetries(environment, 'get_panel', () => ({ context, continuation: panelToken }));
      command = findSendCommand(initial, { panelOnly: false });
    }
  }
  if (command === null) throw new ChatUnavailableError();
  return new AskChatSession(environment, command);
}
