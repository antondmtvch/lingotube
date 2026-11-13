import { test } from 'node:test';
import assert from 'node:assert/strict';
import { STATUS_TEXTS, rateLimitedText, statusTextsFor } from '../src/shared/status_texts.js';
import { uiTexts } from '../src/shared/ui_strings.js';

test('STATUS_TEXTS stays Russian', () => {
  assert.equal(STATUS_TEXTS.notSignedIn, 'Войдите в аккаунт YouTube');
  assert.equal(rateLimitedText(3), 'Чат ограничил запросы. Повтор через 3 мин');
});

test('statusTextsFor returns the statuses of the chosen language', () => {
  const statuses = statusTextsFor('en');
  assert.equal(statuses.notSignedIn, uiTexts('en').notSignedIn);
  assert.deepEqual(Object.keys(statuses).sort(), Object.keys(STATUS_TEXTS).sort());
});
