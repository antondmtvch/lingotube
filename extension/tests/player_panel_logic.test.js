import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  customNamesForMenu,
  languageFromTypedText,
  menuValueForLanguage,
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
