const VIDEO_ID_PATTERN = /^[A-Za-z0-9_-]{11}$/;

/**
 * The video id of a YouTube watch page. Only https://www.youtube.com/watch?v=<id> counts:
 * Shorts, embeds, channel pages, other hosts and malformed ids give null.
 * @param {string} url
 * @returns {string|null}
 */
export function watchVideoIdFromUrl(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.protocol !== 'https:' || parsed.hostname !== 'www.youtube.com' || parsed.pathname !== '/watch') {
    return null;
  }
  const videoId = parsed.searchParams.get('v');
  return videoId !== null && VIDEO_ID_PATTERN.test(videoId) ? videoId : null;
}
