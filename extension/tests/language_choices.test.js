import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  LANGUAGE_CHOICES,
  OTHER_LANGUAGE_VALUE,
  buildLanguageMenu,
  promptLanguageName,
  targetLanguageFromMenuValue,
} from '../src/shared/language_choices.js';

test('LANGUAGE_CHOICES has 30 entries with unique codes', () => {
  assert.equal(LANGUAGE_CHOICES.length, 30);
  assert.equal(new Set(LANGUAGE_CHOICES.map((choice) => choice.code)).size, 30);
  assert.deepEqual(
    LANGUAGE_CHOICES.map((choice) => choice.englishName),
    [
      'English', 'Chinese (Simplified)', 'Chinese (Traditional)', 'Hindi', 'Spanish', 'French',
      'Arabic', 'Bengali', 'Portuguese', 'Russian', 'Urdu', 'Indonesian', 'German', 'Japanese',
      'Turkish', 'Korean', 'Vietnamese', 'Italian', 'Thai', 'Polish', 'Ukrainian', 'Dutch',
      'Persian', 'Hebrew', 'Greek', 'Czech', 'Swedish', 'Romanian', 'Hungarian', 'Kazakh',
    ],
  );
  assert.deepEqual(
    LANGUAGE_CHOICES.filter((choice) => choice.code.startsWith('zh')).map((choice) => choice.code),
    ['zh-Hans', 'zh-Hant'],
  );
});

test('menu: custom names first, "Другой язык…" last', () => {
  const menu = buildLanguageMenu(['Татарский', 'Latin']);
  assert.deepEqual(menu.slice(0, 2), [
    { value: 'custom:Татарский', label: 'Татарский' },
    { value: 'custom:Latin', label: 'Latin' },
  ]);
  assert.equal(menu.length, 2 + 30 + 1);
  assert.deepEqual(menu.at(-1), { value: OTHER_LANGUAGE_VALUE, label: 'Другой язык…' });
  assert.equal(OTHER_LANGUAGE_VALUE, '__other__');
  assert.ok(menu.some((item) => item.value === 'ja' && item.label === '日本語'));
});

test('targetLanguageFromMenuValue maps codes, custom names and rejects the rest', () => {
  assert.deepEqual(targetLanguageFromMenuValue('ja'), { code: 'ja', name: 'Japanese' });
  assert.deepEqual(targetLanguageFromMenuValue('custom:Татарский'), { code: null, name: 'Татарский' });
  assert.equal(targetLanguageFromMenuValue(OTHER_LANGUAGE_VALUE), null);
  assert.equal(targetLanguageFromMenuValue('xx'), null);
  assert.equal(targetLanguageFromMenuValue('custom:   '), null);
});

test('promptLanguageName: "ja" → "Japanese"; a typed name is passed sanitized', () => {
  assert.equal(promptLanguageName({ code: 'ja', name: 'whatever' }), 'Japanese');
  assert.equal(promptLanguageName({ code: null, name: '  Tatar \n  language ' }), 'Tatar language');
});

test('promptLanguageName never returns an empty name', () => {
  assert.equal(promptLanguageName({ code: null, name: '   ' }), 'Russian');
  assert.equal(promptLanguageName({ code: null, name: '' }), 'Russian');
});

test('buildLanguageMenu takes the label of the "other language" item from the argument', () => {
  const otherItem = buildLanguageMenu([], 'Another language…').find((item) => item.value === OTHER_LANGUAGE_VALUE);
  assert.equal(otherItem.label, 'Another language…');
  const defaultItem = buildLanguageMenu([]).find((item) => item.value === OTHER_LANGUAGE_VALUE);
  assert.equal(defaultItem.label, 'Другой язык…');
});
