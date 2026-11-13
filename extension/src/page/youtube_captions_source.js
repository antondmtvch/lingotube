import { timedWordsFromJson3 } from '../shared/json3_captions.js';
import { mergePlayerRequestParameters } from './player_caption_request.js';

export class CaptionsUnavailableError extends Error {
  constructor(message) {
    super(message);
    this.name = 'CaptionsUnavailableError';
  }
}

/**
 * Requests the chosen track with the player's parameters and parses the words.
 * Error texts never contain the URL.
 * @param {object} options
 * @param {{baseUrl: string}} options.track
 * @param {string} options.playerRequestUrl
 * @param {typeof fetch} options.fetch
 * @returns {Promise<import('../shared/json3_captions.js').TimedWord[]>}
 */
export async function fetchCaptionWords({ track, playerRequestUrl, fetch }) {
  const url = mergePlayerRequestParameters(track.baseUrl, playerRequestUrl);
  const response = await fetch(url, { credentials: 'include' });
  const body = await response.text();
  if (!body.trim()) throw new CaptionsUnavailableError('YouTube returned an empty captions body');
  let json3;
  try {
    json3 = JSON.parse(body);
  } catch {
    throw new CaptionsUnavailableError('YouTube returned captions that are not JSON');
  }
  const words = timedWordsFromJson3(json3);
  if (!words.length) throw new CaptionsUnavailableError('YouTube captions contain no words');
  return words;
}
