import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  customNamesForMenu,
  languageFromTypedText,
  menuValueForLanguage,
  placeButtonNextToSubtitlesButton,
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
