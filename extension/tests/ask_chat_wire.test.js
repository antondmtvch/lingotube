import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  findSendCommand,
  findChatPanelToken,
  isSignedIn,
  buildAskBody,
  extractAnswer,
} from '../src/shared/ask_chat_wire.js';

const loadFixture = (name) =>
  JSON.parse(readFileSync(new URL(`../../tests/fixtures/${name}`, import.meta.url), 'utf8'));

test('send command is found in the PAyouchat panel of next_eligible', () => {
  assert.deepEqual(findSendCommand(loadFixture('next_eligible.json')), {
    continuation: 'FAKE_CONTINUATION_1',
    clickTrackingParams: 'FAKE_CTP_1',
  });
});

test('no chat panel → null', () => {
  assert.equal(findSendCommand(loadFixture('next_no_chat.json')), null);
  assert.equal(findSendCommand(loadFixture('next_signed_out.json')), null);
});

test('a command outside the panel is ignored unless panelOnly is false', () => {
  const stray = {
    x: { sendUserQueryCommand: { innertubeCommand: { clickTrackingParams: 'C', continuationCommand: { token: 'T' } } } },
  };
  assert.equal(findSendCommand(stray), null);
  assert.deepEqual(findSendCommand(stray, { panelOnly: false }), { continuation: 'T', clickTrackingParams: 'C' });
});

test('findChatPanelToken returns the first panel token or null', () => {
  const panel = {
    engagementPanelSectionListRenderer: {
      panelIdentifier: 'PAyouchat',
      content: { continuationCommand: { token: 'PANEL_TOK' } },
    },
  };
  assert.equal(findChatPanelToken({ a: [panel] }), 'PANEL_TOK');
  assert.equal(findChatPanelToken(loadFixture('next_no_chat.json')), null);
});

test('signed-out fixture → isSignedIn false', () => {
  assert.equal(isSignedIn(loadFixture('next_eligible.json')), true);
  assert.equal(isSignedIn(loadFixture('next_signed_out.json')), false);
  assert.equal(isSignedIn({}), false);
});

test('extractAnswer returns only youChatItemViewModel text', () => {
  const answer = extractAnswer(loadFixture('get_panel_answer.json'));
  assert.ok(answer.startsWith('Вот полная транскрипция'));
  assert.ok(answer.includes('(0:'));
  for (const junk of ['Text copied to clipboard', 'предложенный вопрос', 'примечание о точности']) {
    assert.ok(!answer.includes(junk));
  }
});

test('extractAnswer gives an empty string when there is no answer', () => {
  assert.equal(extractAnswer({}), '');
});

test('buildAskBody builds the get_panel body', () => {
  const body = buildAskBody({
    context: { client: { clientName: 'WEB' } },
    command: { continuation: 'TOK', clickTrackingParams: 'CTP' },
    prompt: 'привет',
    nowMs: 1700000000000,
  });
  assert.equal(body.continuation, 'TOK');
  assert.deepEqual(body.formData.inputComposerFormData, {
    clientMessageId: 'youchat-1700000000000',
    playerOffsetMs: '0',
    userInputText: 'привет',
  });
  assert.equal(body.context.clickTracking.clickTrackingParams, 'CTP');
});

test('buildAskBody does not mutate the context', () => {
  const context = { client: { clientName: 'WEB' } };
  buildAskBody({ context, command: { continuation: 'T', clickTrackingParams: 'C' }, prompt: 'q', nowMs: 1 });
  assert.deepEqual(context, { client: { clientName: 'WEB' } });
});
