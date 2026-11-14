import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ChatTranslator } from '../src/page/chat_translator.js';

function cue(id) {
  return { id, startMs: id * 1000, endMs: id * 1000 + 900, sourceText: `source ${id}` };
}

/** Fake session answering from a queue; a queued Error is thrown. */
function fakeSession(answers) {
  const prompts = [];
  return {
    prompts,
    async ask(prompt) {
      prompts.push(prompt);
      const answer = answers.shift();
      if (answer instanceof Error) throw answer;
      return answer;
    },
  };
}

const cues = [cue(57), cue(58), cue(59), cue(60)];

test('a complete first answer needs one message', async () => {
  const session = fakeSession(['57\ta\n58\tb\n59\tc\n60\td']);
  const result = await new ChatTranslator({ chatSession: session, languageName: 'Russian' }).translateCues(cues);
  assert.equal(session.prompts.length, 1);
  assert.equal(result.translationsByCueId.size, 4);
  assert.deepEqual(result.failedCueIds, []);
});

test('missing ids are asked once more with only those cues', async () => {
  const session = fakeSession(['57\ta\n58\tb', '59\tc\n60\td']);
  const result = await new ChatTranslator({ chatSession: session, languageName: 'Russian' }).translateCues(cues);
  assert.equal(session.prompts.length, 2);
  assert.ok(session.prompts[1].includes('59\tsource 59'));
  assert.ok(session.prompts[1].includes('60\tsource 60'));
  assert.equal(session.prompts[1].includes('57\tsource 57'), false);
  assert.deepEqual([...result.translationsByCueId.keys()], [57, 58, 59, 60]);
  assert.deepEqual(result.failedCueIds, []);
});

test('ids still missing after the second message are failed, the rest translated', async () => {
  const session = fakeSession(['57\ta\n58\tb', '59\tc']);
  const result = await new ChatTranslator({ chatSession: session, languageName: 'Russian' }).translateCues(cues);
  assert.deepEqual([...result.translationsByCueId.keys()].sort(), [57, 58, 59]);
  assert.deepEqual(result.failedCueIds, [60]);
});

test('at most two messages per call', async () => {
  const session = fakeSession(['garbage', 'more garbage', 'unused']);
  const result = await new ChatTranslator({ chatSession: session, languageName: 'Russian' }).translateCues(cues);
  assert.equal(session.prompts.length, 2);
  assert.deepEqual(result.failedCueIds, [57, 58, 59, 60]);
});

test('an empty cue list sends nothing', async () => {
  const session = fakeSession([]);
  const result = await new ChatTranslator({ chatSession: session, languageName: 'Russian' }).translateCues([]);
  assert.equal(session.prompts.length, 0);
  assert.equal(result.translationsByCueId.size, 0);
});

test('an error from the session propagates', async () => {
  const failure = new Error('boom');
  const session = fakeSession([failure]);
  await assert.rejects(
    new ChatTranslator({ chatSession: session, languageName: 'Russian' }).translateCues(cues),
    failure,
  );
});
