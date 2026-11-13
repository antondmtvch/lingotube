import { createExtensionStorage } from './extension_storage.js';
import { findPlayerElement, readCaptionTracks, readVideoDetails } from './youtube_player.js';
import { capturePlayerCaptionRequestUrl } from './player_caption_request.js';
import { fetchCaptionWords } from './youtube_captions_source.js';
import { chooseCaptionTrack } from '../shared/caption_track_choice.js';

async function checkStorageRoundTrip() {
  const extensionStorage = createExtensionStorage({ window });
  try {
    await extensionStorage.set({ 'lingotube:probe': 'ok' });
    const stored = await extensionStorage.get(['lingotube:probe']);
    await extensionStorage.remove(['lingotube:probe']);
    console.info(
      stored['lingotube:probe'] === 'ok'
        ? 'lingotube: page ready, storage ok'
        : 'lingotube: page ready, storage failed',
    );
  } catch (error) {
    console.info('lingotube: page ready, storage failed', error);
  }
}

/** Debug run: reads the captions once and logs only a summary (never URLs or tokens). */
async function debugReadCaptions() {
  if (location.pathname !== '/watch') return;
  try {
    const playerElement = findPlayerElement(document);
    const track = playerElement && chooseCaptionTrack(readCaptionTracks(playerElement));
    if (!track) {
      console.info('lingotube: captions', { track: null });
      return;
    }
    let forcedByButton = false;
    const playerRequestUrl = await capturePlayerCaptionRequestUrl({
      document,
      expectedVideoId: readVideoDetails(playerElement).videoId,
      performanceObserverClass: PerformanceObserver,
      sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
      onButtonForced: () => {
        forcedByButton = true;
      },
    });
    if (!playerRequestUrl) {
      console.info('lingotube: captions', { track: { languageCode: track.languageCode, kind: track.kind }, error: 'player request not captured', forcedByButton });
      return;
    }
    const words = await fetchCaptionWords({ track, playerRequestUrl, fetch: window.fetch.bind(window) });
    console.info('lingotube: captions', {
      track: { languageCode: track.languageCode, kind: track.kind },
      words: words.length,
      firstStartMs: words[0].startMs,
      lastStartMs: words.at(-1).startMs,
      forcedByButton,
    });
  } catch (error) {
    console.info('lingotube: captions failed', error?.name);
  }
}

checkStorageRoundTrip();
debugReadCaptions();
