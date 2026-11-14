import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ChatTranscriptSource } from '../src/page/chat_transcript_source.js';
import { ChatRateLimitedError } from '../src/shared/chat_errors.js';
import { fillPrompt } from '../src/shared/prompt_texts.js';

function fakeSession(answer) {
  const prompts = [];
  return {
    prompts,
    async ask(prompt) {
      prompts.push(prompt);
      if (answer instanceof Error) throw answer;
      return answer;
    },
  };
}

test('the transcript prompt names the chunk range and the language', async () => {
  const session = fakeSession('(5:02) Привет');
  const source = new ChatTranscriptSource({ chatSession: session, languageName: 'Russian', durationMs: 3725400 });
  await source.requestChunk(1);
  await source.requestChunk(12);
  assert.deepEqual(session.prompts, [
    fillPrompt('transcript_translated', { start: '5:00', end: '10:00', language: 'Russian' }),
    fillPrompt('transcript_translated', { start: '1:00:00', end: '1:02:06', language: 'Russian' }),
  ]);
});

test('lines are parsed, kept inside the chunk and given reading-time ends', async () => {
  const session = fakeSession('Вот перевод:\n(4:58) old\n(5:02) Hello\n(5:02) Привет\n(5:04) Пока\n(10:00) next chunk');
  const source = new ChatTranscriptSource({ chatSession: session, languageName: 'Russian', durationMs: 1800000 });
  assert.deepEqual(await source.requestChunk(1), [
    { startMs: 302000, endMs: 303500, text: 'Привет' },
    { startMs: 304000, endMs: 305500, text: 'Пока' },
  ]);
});

test('an answer without timestamps gives no lines; chat errors propagate', async () => {
  const empty = new ChatTranscriptSource({ chatSession: fakeSession('Не могу помочь.'), languageName: 'Russian', durationMs: 600000 });
  assert.deepEqual(await empty.requestChunk(0), []);
  const limited = new ChatTranscriptSource({ chatSession: fakeSession(new ChatRateLimitedError(9)), languageName: 'Russian', durationMs: 600000 });
  await assert.rejects(limited.requestChunk(0), ChatRateLimitedError);
});
