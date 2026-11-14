// Hides YouTube's own caption text with CSS (the rule lives in overlay.css) without
// touching the subtitles button or the user's caption settings.

export const HIDE_NATIVE_CAPTIONS_CLASS = 'lingotube-hide-native-captions';

/** @param {Element|null|undefined} playerElement */
export function hideNativeCaptions(playerElement) {
  playerElement?.classList.add(HIDE_NATIVE_CAPTIONS_CLASS);
}

/** @param {Element|null|undefined} playerElement */
export function showNativeCaptions(playerElement) {
  playerElement?.classList.remove(HIDE_NATIVE_CAPTIONS_CLASS);
}
