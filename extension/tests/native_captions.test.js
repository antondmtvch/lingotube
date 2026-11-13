import assert from 'node:assert/strict';
import { test } from 'node:test';
import { HIDE_NATIVE_CAPTIONS_CLASS, hideNativeCaptions, showNativeCaptions } from '../src/page/native_captions.js';

function createFakePlayer() {
  const classes = new Set();
  return {
    classes,
    classList: { add: (name) => classes.add(name), remove: (name) => classes.delete(name) },
  };
}

test('hideNativeCaptions adds the hiding class and showNativeCaptions removes it', () => {
  const player = createFakePlayer();
  hideNativeCaptions(player);
  assert.deepEqual([...player.classes], [HIDE_NATIVE_CAPTIONS_CLASS]);
  showNativeCaptions(player);
  assert.equal(player.classes.size, 0);
});

test('the hiding class name matches the overlay stylesheet rule', () => {
  assert.equal(HIDE_NATIVE_CAPTIONS_CLASS, 'lingotube-hide-native-captions');
});

test('a missing player element does not throw', () => {
  for (const missing of [null, undefined]) {
    assert.doesNotThrow(() => hideNativeCaptions(missing));
    assert.doesNotThrow(() => showNativeCaptions(missing));
  }
});
