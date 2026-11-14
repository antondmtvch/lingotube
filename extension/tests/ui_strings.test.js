import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  UI_LANGUAGES,
  FALLBACK_UI_LANGUAGE,
  pickUiLanguage,
  isRightToLeft,
  uiTexts,
} from '../src/shared/ui_strings.js';

test('every supported language has exactly the keys of Russian and non-empty strings', () => {
  const keys = Object.keys(uiTexts('ru')).sort();
  for (const code of UI_LANGUAGES) {
    assert.deepEqual(Object.keys(uiTexts(code)).sort(), keys, code);
    for (const key of keys) assert.ok(String(uiTexts(code)[key]).length > 0, `${code}.${key}`);
  }
});

test('the set has the 30 keys of the plan and the fallback is English', () => {
  assert.equal(Object.keys(uiTexts('ru')).length, 30);
  assert.equal(FALLBACK_UI_LANGUAGE, 'en');
  assert.equal(UI_LANGUAGES.length, 10);
});

test('pickUiLanguage: exact tags, primary subtag, fallback', () => {
  assert.equal(pickUiLanguage('ru-RU'), 'ru');
  assert.equal(pickUiLanguage('pt-PT'), 'pt-BR');
  assert.equal(pickUiLanguage('pt-BR'), 'pt-BR');
  assert.equal(pickUiLanguage('zh-TW'), 'zh-CN');
  assert.equal(pickUiLanguage('zh-cn'), 'zh-CN');
  assert.equal(pickUiLanguage('en-GB'), 'en');
  assert.equal(pickUiLanguage('xx-YY'), 'en');
  assert.equal(pickUiLanguage(''), 'en');
  assert.equal(pickUiLanguage(undefined), 'en');
});

test('pickUiLanguage never throws on wrong types', () => {
  for (const value of [null, 5, {}, [], 'C']) assert.equal(pickUiLanguage(value), 'en');
});

test('only Arabic is right-to-left', () => {
  assert.equal(isRightToLeft('ar'), true);
  for (const code of UI_LANGUAGES.filter((c) => c !== 'ar')) assert.equal(isRightToLeft(code), false);
});

test('rateLimited puts the number into the text in every language', () => {
  for (const code of UI_LANGUAGES) assert.match(uiTexts(code).rateLimited(7), /7/, code);
});

test('uiTexts of an unknown code is the English set', () => {
  assert.equal(uiTexts('xx').subtitlesLabel, uiTexts('en').subtitlesLabel);
});

test('inherited object property names are unknown codes and fall back to English', () => {
  assert.equal(pickUiLanguage('constructor'), 'en');
  assert.equal(pickUiLanguage('__proto__'), 'en');
  assert.equal(uiTexts('toString').subtitlesLabel, uiTexts('en').subtitlesLabel);
  assert.doesNotThrow(() => uiTexts('__proto__').rateLimited(1));
  assert.equal(uiTexts('constructor').subtitlesLabel, uiTexts('en').subtitlesLabel);
});
