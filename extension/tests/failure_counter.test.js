import { test } from 'node:test';
import assert from 'node:assert/strict';
import { FailureCounter, stopReasonOfChatError } from '../src/shared/failure_counter.js';
import {
  ChatRateLimitedError,
  ChatRequestFailedError,
  ChatUnavailableError,
  NotSignedInError,
} from '../src/shared/chat_errors.js';

test('three failures in a row reach the limit; a success starts the count again', () => {
  const counter = new FailureCounter();
  assert.equal(counter.recordFailure(), false);
  assert.equal(counter.recordFailure(), false);
  counter.recordSuccess();
  assert.equal(counter.recordFailure(), false);
  assert.equal(counter.recordFailure(), false);
  assert.equal(counter.recordFailure(), true);
  counter.reset();
  assert.equal(counter.recordFailure(), false);
});

test('chat errors that stop requests map to their stop reasons; others count as failures', () => {
  assert.equal(stopReasonOfChatError(new ChatRateLimitedError(5)), 'rate-limited');
  assert.equal(stopReasonOfChatError(new NotSignedInError()), 'not-signed-in');
  assert.equal(stopReasonOfChatError(new ChatUnavailableError()), 'chat-unavailable');
  assert.equal(stopReasonOfChatError(new ChatRequestFailedError()), null);
  assert.equal(stopReasonOfChatError(new Error('anything')), null);
});

test('the translation pump and the transcript pump both count with the shared counter', async () => {
  const { readFile } = await import('node:fs/promises');
  for (const file of ['translation_pump.js', 'transcript_chunk_pump.js']) {
    const source = await readFile(new URL(`../src/shared/${file}`, import.meta.url), 'utf8');
    assert.match(source, /from '\.\/failure_counter\.js'/, file);
    assert.match(source, /new FailureCounter\(/, file);
  }
});
