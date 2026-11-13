import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CHAT_TRANSCRIPT_SOURCE_KEY, captionSourceKey, languageCacheKey, translationCacheKey } from '../src/shared/cache_key.js';
import { PROMPT_VERSION } from '../src/shared/prompt_texts.js';
import { CUE_RULES_VERSION } from '../src/shared/sentence_cues.js';

const base = { videoId: 'abc', language: { code: 'ru', name: 'Russian' }, sourceKey: 'en.asr' };

test('cache key has the documented shape', () => {
  assert.equal(translationCacheKey(base), `cache:abc|ru|en.asr|p${PROMPT_VERSION}|c${CUE_RULES_VERSION}`);
});

test('cache key differs by video, language and source', () => {
  const keys = new Set([
    translationCacheKey(base),
    translationCacheKey({ ...base, videoId: 'other' }),
    translationCacheKey({ ...base, language: { code: 'ja', name: 'Japanese' } }),
    translationCacheKey({ ...base, sourceKey: CHAT_TRANSCRIPT_SOURCE_KEY }),
  ]);
  assert.equal(keys.size, 4);
  assert.equal(CHAT_TRANSCRIPT_SOURCE_KEY, 'chat');
});

test('cache key carries the prompt version and the cue rules version', () => {
  const key = translationCacheKey(base);
  assert.ok(key.includes(`|p${PROMPT_VERSION}|`));
  assert.ok(key.endsWith(`|c${CUE_RULES_VERSION}`));
});

test('typed languages "Татарский " and "татарский" share one cache key', () => {
  const first = { code: 'custom', name: 'Татарский ' };
  const second = { code: 'custom', name: 'татарский' };
  assert.equal(languageCacheKey(first), 'custom:татарский');
  assert.equal(translationCacheKey({ ...base, language: first }), translationCacheKey({ ...base, language: second }));
});

test('captionSourceKey joins language code and kind', () => {
  assert.equal(captionSourceKey({ languageCode: 'en', kind: 'asr', baseUrl: 'x' }), 'en.asr');
});
