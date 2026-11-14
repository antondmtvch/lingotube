import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  TEXT_COLOR_CSS,
  appearanceVariables,
  shouldShowHint,
  steppedBackgroundOpacity,
  customNamesForMenu,
  languageFromTypedText,
  menuValueForLanguage,
  placeButtonNextToSubtitlesButton,
  rememberTypedLanguage,
  selectValueAfterClose,
  steppedTextScale,
} from '../src/shared/player_panel_logic.js';
import { targetLanguageFromMenuValue } from '../src/shared/language_choices.js';

test('typed text becomes a language without a code, with spaces collapsed', () => {
  assert.deepEqual(languageFromTypedText('  Brazilian   Portuguese '), { code: null, name: 'Brazilian Portuguese' });
});

test('empty or whitespace-only typed text is not a language', () => {
  assert.equal(languageFromTypedText(''), null);
  assert.equal(languageFromTypedText(' \t\n '), null);
});

test('a menu value round-trips to the same language', () => {
  for (const language of [{ code: 'ru', name: 'Russian' }, { code: null, name: 'Esperanto' }]) {
    assert.deepEqual(targetLanguageFromMenuValue(menuValueForLanguage(language)), language);
  }
});

test('the current typed language is added to the menu names when not remembered', () => {
  assert.deepEqual(customNamesForMenu(['Latin'], { code: null, name: 'Esperanto' }), ['Esperanto', 'Latin']);
});

test('the current typed language is not duplicated when remembered in another case', () => {
  assert.deepEqual(customNamesForMenu(['esperanto'], { code: null, name: 'Esperanto' }), ['esperanto']);
});

test('a listed current language leaves the remembered names as they are', () => {
  assert.deepEqual(customNamesForMenu(['Latin'], { code: 'ru', name: 'Russian' }), ['Latin']);
});

test('text scale moves by 0.2 without float drift and stays in 0.6..2', () => {
  assert.equal(steppedTextScale(1, 1), 1.2);
  assert.equal(steppedTextScale(1.2, 1), 1.4);
  assert.equal(steppedTextScale(1, -1), 0.8);
  assert.equal(steppedTextScale(2, 1), 2);
  assert.equal(steppedTextScale(0.6, -1), 0.6);
});

test('after the input is abandoned the select shows the language in use, not "other"', () => {
  assert.equal(selectValueAfterClose({ code: 'ru', name: 'Russian' }), 'ru');
  assert.equal(selectValueAfterClose({ code: null, name: 'Esperanto' }), 'custom:Esperanto');
  assert.notEqual(selectValueAfterClose({ code: 'de', name: 'German' }), '__other__');
});

function fakeParent(name) {
  const parent = {
    name,
    firstChild: { id: 'first' },
    inserted: [],
    insertBefore(node, reference) {
      if (reference !== null && !this.children.includes(reference)) throw new Error('NotFoundError');
      this.inserted.push({ node, reference });
    },
    children: [],
  };
  return parent;
}

test('a nested subtitles button gets the new button in its own parent without throwing', () => {
  const rightControls = fakeParent('right');
  const wrapper = fakeParent('wrapper');
  const subtitlesButton = { parentNode: wrapper };
  wrapper.children.push(subtitlesButton);
  const button = {};
  placeButtonNextToSubtitlesButton({ rightControls, subtitlesButton, button });
  assert.deepEqual(wrapper.inserted, [{ node: button, reference: subtitlesButton }]);
  assert.deepEqual(rightControls.inserted, []);
});

test('without a subtitles button the new button goes first among the right controls', () => {
  const rightControls = fakeParent('right');
  rightControls.children.push(rightControls.firstChild);
  const button = {};
  placeButtonNextToSubtitlesButton({ rightControls, subtitlesButton: null, button });
  assert.deepEqual(rightControls.inserted, [{ node: button, reference: rightControls.firstChild }]);
});

test('confirming a typed name equal to the current custom language leaves the select on that language', () => {
  const current = { code: null, name: 'Esperanto' };
  const typed = languageFromTypedText('  Esperanto ');
  assert.equal(selectValueAfterClose(current), menuValueForLanguage(typed));
  assert.equal(selectValueAfterClose(current), 'custom:Esperanto');
});

test('a typed language is remembered newest first, without case-insensitive duplicates, at most five', () => {
  assert.deepEqual(rememberTypedLanguage(['Klingon', 'Elvish'], { code: null, name: 'elvish' }), ['elvish', 'Klingon']);
  assert.deepEqual(
    rememberTypedLanguage(['a', 'b', 'c', 'd', 'e'], { code: null, name: 'f' }),
    ['f', 'a', 'b', 'c', 'd'],
  );
  assert.deepEqual(rememberTypedLanguage(['Klingon'], { code: 'de', name: 'German' }), ['Klingon']);
});

test('appearance: the three text colour presets map to fixed CSS colours', () => {
  assert.equal(TEXT_COLOR_CSS.white, '#fff');
  assert.equal(TEXT_COLOR_CSS.yellow, '#ffd400');
  assert.equal(TEXT_COLOR_CSS.cyan, '#7fd3ff');
});

test('appearance: variables carry the colour and the background opacity', () => {
  assert.deepEqual(appearanceVariables({ textColor: 'yellow', backgroundOpacity: 0.4 }), {
    '--lingotube-text-color': '#ffd400',
    '--lingotube-bg-opacity': '0.4',
  });
});

test('appearance: background opacity steps by 0.05 and stops at the ends', () => {
  assert.equal(steppedBackgroundOpacity(0.75, 1), 0.8);
  assert.equal(steppedBackgroundOpacity(0.75, -1), 0.7);
  assert.equal(steppedBackgroundOpacity(1, 1), 1);
  assert.equal(steppedBackgroundOpacity(0, -1), 0);
  assert.equal(steppedBackgroundOpacity(0.1, -1), 0.05);
});

test('hint: shown only before the first enable and only when it was not seen', () => {
  assert.equal(shouldShowHint({ hintSeen: false, enabled: false }), true);
  assert.equal(shouldShowHint({ hintSeen: true, enabled: false }), false);
  assert.equal(shouldShowHint({ hintSeen: false, enabled: true }), false);
});
