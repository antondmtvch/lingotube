import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { sapisidHashHeader, openAskChat } from '../src/page/ask_chat_client.js';
import {
  ChatUnavailableError,
  NotSignedInError,
  ChatRateLimitedError,
  ChatRequestFailedError,
} from '../src/shared/chat_errors.js';

const loadFixture = (name) =>
  JSON.parse(readFileSync(new URL(`../../tests/fixtures/${name}`, import.meta.url), 'utf8'));

const COOKIE_TEXT = 'a=1; SAPISID=SECRET_SAPISID; b=2';
const sha1Hex = async (text) => createHash('sha1').update(text).digest('hex');
const CONTEXT = { client: { clientName: 'WEB', clientVersion: '2.2026', visitorData: 'SECRET_VISITOR' } };

/** Fake fetch: replies are queued; each is {status, json} or an Error to throw. */
function makeFetch(replies) {
  const calls = [];
  const queue = [...replies];
  const fetch = async (url, init) => {
    calls.push({ url, init, body: JSON.parse(init.body) });
    const reply = queue.shift();
    if (reply instanceof Error) throw reply;
    return {
      status: reply.status,
      json: async () => {
        if (reply.json === undefined) throw new SyntaxError('bad json');
        return reply.json;
      },
    };
  };
  fetch.calls = calls;
  return fetch;
}

function makeGate() {
  const gate = {
    runs: 0,
    cooldowns: 0,
    run: async (send) => {
      gate.runs += 1;
      return send();
    },
    startCooldown: () => {
      gate.cooldowns += 1;
    },
    cooldownRemainingMs: () => 30000,
  };
  return gate;
}

const answerReply = { status: 200, json: loadFixture('get_panel_answer.json') };
const eligibleReply = { status: 200, json: loadFixture('next_eligible.json') };

function open(replies, overrides = {}) {
  const fetch = makeFetch(replies);
  const gate = makeGate();
  const promise = openAskChat({
    videoId: 'VID',
    context: CONTEXT,
    sessionIndex: 0,
    fetch,
    gate,
    cookieText: COOKIE_TEXT,
    now: () => 1700000000000,
    sha1Hex,
    ...overrides,
  });
  return { fetch, gate, promise };
}

test('sapisidHashHeader gives "SAPISIDHASH <ts>_<sha1 of ts sapisid origin>"', async () => {
  const header = await sapisidHashHeader({
    cookieText: COOKIE_TEXT,
    origin: 'https://www.youtube.com',
    nowSeconds: 1700000000,
    sha1Hex,
  });
  const expected = createHash('sha1').update('1700000000 SECRET_SAPISID https://www.youtube.com').digest('hex');
  assert.equal(header, `SAPISIDHASH 1700000000_${expected}`);
});

test('sapisidHashHeader falls back to __Secure-3PAPISID and throws NotSignedInError without cookies', async () => {
  const header = await sapisidHashHeader({
    cookieText: '__Secure-3PAPISID=ALT',
    origin: 'o',
    nowSeconds: 5,
    sha1Hex,
  });
  assert.equal(header, `SAPISIDHASH 5_${createHash('sha1').update('5 ALT o').digest('hex')}`);
  await assert.rejects(
    sapisidHashHeader({ cookieText: 'x=1', origin: 'o', nowSeconds: 5, sha1Hex }),
    NotSignedInError,
  );
});

test('ask posts to /youtubei/v1/get_panel?prettyPrint=false with the Authorization header', async () => {
  const { fetch, promise } = open([eligibleReply, answerReply]);
  const session = await promise;
  const answer = await session.ask('hello');
  assert.ok(answer.startsWith('Вот полная транскрипция'));
  const next = fetch.calls[0];
  assert.equal(next.url, '/youtubei/v1/next?prettyPrint=false');
  assert.deepEqual(next.body, { context: CONTEXT, videoId: 'VID' });
  const call = fetch.calls[1];
  assert.equal(call.url, '/youtubei/v1/get_panel?prettyPrint=false');
  assert.equal(call.init.method, 'POST');
  assert.equal(call.init.credentials, 'include');
  assert.match(call.init.headers.Authorization, /^SAPISIDHASH 1700000000_[0-9a-f]{40}$/);
  assert.equal(call.init.headers['X-Origin'], 'https://www.youtube.com');
  assert.equal(call.init.headers['X-Goog-AuthUser'], '0');
  assert.equal(call.init.headers['X-Youtube-Client-Name'], '1');
  assert.equal(call.init.headers['X-Youtube-Client-Version'], '2.2026');
  assert.equal(call.init.headers['X-Goog-Visitor-Id'], 'SECRET_VISITOR');
  assert.equal(call.body.continuation, 'FAKE_CONTINUATION_1');
  assert.equal(call.body.formData.inputComposerFormData.userInputText, 'hello');
  assert.ok(call.init.signal);
});

test('5xx twice then 200 → answer returned after exactly 3 requests', async () => {
  const { fetch, gate, promise } = open([eligibleReply, { status: 503, json: {} }, new Error('net'), answerReply]);
  const session = await promise;
  const answer = await session.ask('q');
  assert.ok(answer.length > 0);
  assert.equal(fetch.calls.length, 4); // next + 3 get_panel
  assert.equal(gate.runs, 4);
  const prompts = fetch.calls.slice(1).map((c) => c.body.formData.inputComposerFormData.userInputText);
  assert.deepEqual(prompts, ['q', 'q', 'q']);
});

test('non-JSON and empty answers are retried too', async () => {
  const { fetch, promise } = open([eligibleReply, { status: 200 }, { status: 200, json: {} }, answerReply]);
  const session = await promise;
  assert.ok((await session.ask('q')).length > 0);
  assert.equal(fetch.calls.length, 4);
});

test('three failures → ChatRequestFailedError whose message has no token, cookie or URL', async () => {
  const { fetch, promise } = open([
    eligibleReply,
    { status: 500, json: { secret: 'SECRET_BODY' } },
    { status: 502, json: {} },
    new Error('https://www.youtube.com/youtubei/v1/get_panel SECRET_SAPISID'),
  ]);
  const session = await promise;
  const error = await session.ask('q').then(
    () => null,
    (e) => e,
  );
  assert.ok(error instanceof ChatRequestFailedError);
  assert.equal(fetch.calls.length, 4);
  for (const secret of ['SECRET', 'FAKE_', 'youtube', 'SAPISIDHASH', 'http']) {
    assert.ok(!error.message.includes(secret), secret);
  }
});

test('429 → startCooldown called once, ChatRateLimitedError, no retry', async () => {
  const { fetch, gate, promise } = open([eligibleReply, { status: 429, json: {} }]);
  const session = await promise;
  const error = await session.ask('q').then(
    () => null,
    (e) => e,
  );
  assert.ok(error instanceof ChatRateLimitedError);
  assert.equal(error.retryAtMs, 1700000000000 + 30000);
  assert.equal(gate.cooldowns, 1);
  assert.equal(fetch.calls.length, 2);
});

test('403 → NotSignedInError', async () => {
  const { promise } = open([eligibleReply, { status: 403, json: {} }]);
  const session = await promise;
  await assert.rejects(session.ask('q'), NotSignedInError);
});

test('other 4xx → ChatRequestFailedError without retry', async () => {
  const { fetch, promise } = open([eligibleReply, { status: 400, json: {} }]);
  const session = await promise;
  await assert.rejects(session.ask('q'), ChatRequestFailedError);
  assert.equal(fetch.calls.length, 2);
});

test('next without a panel → ChatUnavailableError', async () => {
  const { promise } = open([{ status: 200, json: loadFixture('next_no_chat.json') }]);
  await assert.rejects(promise, ChatUnavailableError);
});

test('signed-out next → NotSignedInError', async () => {
  const { promise } = open([{ status: 200, json: loadFixture('next_signed_out.json') }]);
  await assert.rejects(promise, NotSignedInError);
});

test('no command in next but a panel token → the empty initial get_panel supplies it', async () => {
  const eligible = loadFixture('next_eligible.json');
  const noCommand = {
    responseContext: eligible.responseContext,
    x: {
      engagementPanelSectionListRenderer: {
        panelIdentifier: 'PAyouchat',
        content: { continuationCommand: { token: 'PANEL_TOK' } },
      },
    },
  };
  const initial = {
    y: { sendUserQueryCommand: { innertubeCommand: { clickTrackingParams: 'C2', continuationCommand: { token: 'T2' } } } },
  };
  const { fetch, promise } = open([{ status: 200, json: noCommand }, { status: 200, json: initial }, answerReply]);
  const session = await promise;
  assert.deepEqual(fetch.calls[1].body, { context: CONTEXT, continuation: 'PANEL_TOK' });
  await session.ask('q');
  assert.equal(fetch.calls[2].body.continuation, 'T2');
});

test('the second ask uses the send command from the first reply', async () => {
  const fresh = {
    ...loadFixture('get_panel_answer.json'),
    fresh: {
      sendUserQueryCommand: { innertubeCommand: { clickTrackingParams: 'CTP_NEW', continuationCommand: { token: 'TOK_NEW' } } },
    },
  };
  const { fetch, promise } = open([eligibleReply, { status: 200, json: fresh }, answerReply]);
  const session = await promise;
  await session.ask('one');
  await session.ask('two');
  assert.equal(fetch.calls[2].body.continuation, 'TOK_NEW');
  assert.equal(fetch.calls[2].body.context.clickTracking.clickTrackingParams, 'CTP_NEW');
});

test('every retry sends the same body (same clientMessageId and formData)', async () => {
  let clock = 1700000000000;
  const { fetch, promise } = open([eligibleReply, { status: 503, json: {} }, { status: 503, json: {} }, answerReply], {
    now: () => (clock += 1000),
  });
  const session = await promise;
  await session.ask('q');
  const askBodies = fetch.calls.slice(1).map((c) => c.body);
  assert.equal(askBodies.length, 3);
  assert.deepEqual(askBodies[1].formData, askBodies[0].formData);
  assert.deepEqual(askBodies[2].formData, askBodies[0].formData);
});

test('the Authorization timestamp is taken inside the gate, right before fetch', async () => {
  let clock = 1700000000000;
  const gate = makeGate();
  gate.run = async (send) => {
    clock += 60000; // the gate holds the send for a minute
    return send();
  };
  const { fetch, promise } = open([eligibleReply], { gate, now: () => clock });
  await promise;
  assert.match(fetch.calls[0].init.headers.Authorization, /^SAPISIDHASH 1700000060_/);
});

test('a gate rejecting with ChatRateLimitedError propagates after one gate.run, no retry', async () => {
  const { gate, promise } = open([eligibleReply]);
  await promise;
  const limited = new ChatRateLimitedError(123);
  const failingGate = { ...makeGate(), runs: 0 };
  failingGate.run = async () => {
    failingGate.runs += 1;
    throw limited;
  };
  const fetch = makeFetch([]);
  await assert.rejects(
    openAskChat({ videoId: 'V', context: CONTEXT, sessionIndex: 0, fetch, gate: failingGate, cookieText: COOKIE_TEXT, now: () => 1, sha1Hex }),
    (error) => error === limited,
  );
  assert.equal(failingGate.runs, 1);
  assert.equal(fetch.calls.length, 0);
  assert.ok(gate);
});

test('ask: a gate rejection with a generic Error propagates unchanged without retry', async () => {
  const { fetch, gate, promise } = open([eligibleReply]);
  const session = await promise;
  const boom = new Error('lock aborted');
  gate.run = async () => {
    gate.runs += 1;
    throw boom;
  };
  const runsBefore = gate.runs;
  await assert.rejects(session.ask('q'), (error) => error === boom);
  assert.equal(gate.runs, runsBefore + 1);
  assert.equal(fetch.calls.length, 1);
});
