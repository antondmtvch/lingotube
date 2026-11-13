import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ChatRequestGate } from '../src/page/chat_request_gate.js';
import { ChatRateLimitedError } from '../src/shared/chat_errors.js';

const LAST_START_KEY = 'lingotube:lastChatRequestStartedAtMs';
const COOLDOWN_KEY = 'lingotube:chatCooldownUntilMs';

/** In-memory Web Locks fake: exclusive locks per name, granted in FIFO order. */
function makeLockManager() {
  const tails = new Map();
  return {
    request(name, callback) {
      const previous = tails.get(name) ?? Promise.resolve();
      const result = previous.then(() => callback());
      tails.set(name, result.then(() => {}, () => {}));
      return result;
    },
  };
}

function makeStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return {
    map,
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => map.set(key, String(value)),
    removeItem: (key) => map.delete(key),
  };
}

/** Manual clock shared by all tabs; sleep advances it instead of waiting. */
function makeClock(start = 1_000_000) {
  const clock = { time: start };
  clock.now = () => clock.time;
  clock.sleep = async (ms) => {
    clock.time += ms;
  };
  return clock;
}

function makeGate({ lockManager, keyValueStorage, clock, visible = () => true, waitUntilTabVisible, sleep }) {
  return new ChatRequestGate({
    lockManager,
    keyValueStorage,
    isTabVisible: visible,
    waitUntilTabVisible: waitUntilTabVisible ?? (async () => {}),
    now: clock.now,
    sleep: sleep ?? clock.sleep,
  });
}

function makeTabs() {
  const lockManager = makeLockManager();
  const keyValueStorage = makeStorage();
  const clock = makeClock();
  const tab = () => makeGate({ lockManager, keyValueStorage, clock });
  return { lockManager, keyValueStorage, clock, tabA: tab(), tabB: tab() };
}

test('two gates sharing lock and storage start their requests at least 5000 ms apart', async () => {
  const { clock, tabA, tabB } = makeTabs();
  const starts = [];
  const send = async () => {
    starts.push(clock.now());
  };
  await Promise.all([tabA.run(send), tabB.run(send), tabA.run(send)]);
  assert.equal(starts.length, 3);
  assert.equal(starts[1] - starts[0], 5000);
  assert.equal(starts[2] - starts[1], 5000);
});

test('requests never overlap: the second starts after the first settles', async () => {
  const { tabA, tabB } = makeTabs();
  const events = [];
  let releaseFirst;
  const first = tabA.run(async () => {
    events.push('first start');
    await new Promise((resolve) => (releaseFirst = resolve));
    events.push('first end');
  });
  const second = tabB.run(async () => {
    events.push('second start');
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(events, ['first start']);
  releaseFirst();
  await Promise.all([first, second]);
  assert.deepEqual(events, ['first start', 'first end', 'second start']);
});

test('run returns the result of sendRequest unchanged', async () => {
  const { tabA } = makeTabs();
  assert.equal(await tabA.run(async () => 'answer'), 'answer');
});

test('a cooldown started in one gate makes the other throw ChatRateLimitedError with retryAtMs', async () => {
  const { clock, tabA, tabB } = makeTabs();
  tabA.startCooldown();
  assert.equal(tabA.cooldownRemainingMs(), 600000);
  let sent = false;
  await assert.rejects(
    tabB.run(async () => {
      sent = true;
    }),
    (error) => error instanceof ChatRateLimitedError && error.retryAtMs === clock.now() + 600000,
  );
  assert.equal(sent, false);
});

test('a cooldown started while a request waited in the queue stops it without sending', async () => {
  const { tabA, tabB } = makeTabs();
  let releaseFirst;
  const first = tabA.run(() => new Promise((resolve) => (releaseFirst = resolve)));
  let sent = false;
  const second = tabB.run(async () => {
    sent = true;
  });
  const secondOutcome = assert.rejects(second, ChatRateLimitedError);
  await new Promise((resolve) => setImmediate(resolve));
  tabA.startCooldown();
  releaseFirst();
  await first;
  await secondOutcome;
  assert.equal(sent, false);
});

test('the cooldown ends after 600000 ms', async () => {
  const { clock, tabA, tabB } = makeTabs();
  tabA.startCooldown();
  clock.time += 599999;
  assert.equal(tabB.cooldownRemainingMs(), 1);
  clock.time += 1;
  assert.equal(tabB.cooldownRemainingMs(), 0);
  assert.equal(await tabB.run(async () => 'ok'), 'ok');
});

test('clearCooldown lets the next request through', async () => {
  const { tabA, tabB } = makeTabs();
  tabA.startCooldown();
  tabB.clearCooldown();
  assert.equal(tabA.cooldownRemainingMs(), 0);
  assert.equal(await tabA.run(async () => 'ok'), 'ok');
});

test('a hidden tab waits and sends nothing until visible', async () => {
  const lockManager = makeLockManager();
  const keyValueStorage = makeStorage();
  const clock = makeClock();
  let visible = false;
  let becomeVisible;
  const gate = makeGate({
    lockManager,
    keyValueStorage,
    clock,
    visible: () => visible,
    waitUntilTabVisible: () =>
      new Promise((resolve) => {
        becomeVisible = () => {
          visible = true;
          resolve();
        };
      }),
  });
  let sent = false;
  const outcome = gate.run(async () => {
    sent = true;
    return 'done';
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(sent, false);
  becomeVisible();
  assert.equal(await outcome, 'done');
  assert.equal(sent, true);
});

test('a rejected request releases the lock and propagates its error unchanged', async () => {
  const { tabA, tabB } = makeTabs();
  const failure = new Error('boom');
  await assert.rejects(tabA.run(async () => { throw failure; }), (error) => error === failure);
  assert.equal(await tabB.run(async () => 'next'), 'next');
});

test('garbage in storage is treated as no cooldown and no last start', async () => {
  const lockManager = makeLockManager();
  const keyValueStorage = makeStorage({ [LAST_START_KEY]: 'abc', [COOLDOWN_KEY]: 'NaN' });
  const clock = makeClock();
  const gate = makeGate({ lockManager, keyValueStorage, clock });
  assert.equal(gate.cooldownRemainingMs(), 0);
  const before = clock.now();
  assert.equal(await gate.run(async () => 'ok'), 'ok');
  assert.equal(clock.now(), before);
});

test('only the two timestamps are stored', async () => {
  const { keyValueStorage, tabA } = makeTabs();
  await tabA.run(async () => {});
  tabA.startCooldown();
  assert.deepEqual([...keyValueStorage.map.keys()].sort(), [COOLDOWN_KEY, LAST_START_KEY]);
});

test('throwing storage does not crash the gate and the in-memory last start still paces', async () => {
  const lockManager = makeLockManager();
  const clock = makeClock();
  const throwing = () => {
    throw new Error('storage disabled');
  };
  const gate = makeGate({
    lockManager,
    keyValueStorage: { getItem: throwing, setItem: throwing, removeItem: throwing },
    clock,
  });
  assert.equal(gate.cooldownRemainingMs(), 0);
  gate.clearCooldown();
  const starts = [];
  await gate.run(async () => starts.push(clock.now()));
  await gate.run(async () => starts.push(clock.now()));
  assert.equal(starts[1] - starts[0], 5000);
});

test('a last start in the future (clock moved back or garbage) makes the gate wait at most 5000 ms', async () => {
  for (const futureValue of ['1e18', String(1_000_000 + 3_600_000)]) {
    const lockManager = makeLockManager();
    const keyValueStorage = makeStorage({ [LAST_START_KEY]: futureValue });
    const clock = makeClock();
    const gate = makeGate({ lockManager, keyValueStorage, clock });
    const before = clock.now();
    await gate.run(async () => {});
    assert.ok(clock.now() - before <= 5000);
  }
});

test('a cooldown far in the future is capped at 600000 ms', () => {
  for (const futureValue of ['1e18', String(1_000_000 + 3_600_000)]) {
    const keyValueStorage = makeStorage({ [COOLDOWN_KEY]: futureValue });
    const gate = makeGate({ lockManager: makeLockManager(), keyValueStorage, clock: makeClock() });
    assert.equal(gate.cooldownRemainingMs(), 600000);
  }
});

test('a tab hidden during the 5 s gap sends nothing until visible again, then sends once', async () => {
  const lockManager = makeLockManager();
  const keyValueStorage = makeStorage();
  const clock = makeClock();
  let visible = true;
  let becomeVisible;
  const gate = makeGate({
    lockManager,
    keyValueStorage,
    clock,
    visible: () => visible,
    waitUntilTabVisible: () =>
      new Promise((resolve) => {
        becomeVisible = () => {
          visible = true;
          resolve();
        };
      }),
    sleep: async (ms) => {
      clock.time += ms;
      visible = false;
    },
  });
  await gate.run(async () => {});
  let sends = 0;
  const outcome = gate.run(async () => ++sends);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(sends, 0);
  becomeVisible();
  await outcome;
  assert.equal(sends, 1);
});

test('a cooldown started by another gate during the gap sleep stops the request without sending', async () => {
  const { lockManager, keyValueStorage, clock, tabB } = makeTabs();
  const tabA = makeGate({
    lockManager,
    keyValueStorage,
    clock,
    sleep: async (ms) => {
      clock.time += ms;
      tabB.startCooldown();
    },
  });
  await tabA.run(async () => {});
  let sent = false;
  await assert.rejects(
    tabA.run(async () => {
      sent = true;
    }),
    ChatRateLimitedError,
  );
  assert.equal(sent, false);
});

test('with storage that cannot write, a cooldown is still kept in this tab until cleared', async () => {
  const clock = makeClock();
  const storage = makeStorage();
  storage.setItem = () => {
    throw new Error('storage disabled');
  };
  const gate = makeGate({ lockManager: makeLockManager(), keyValueStorage: storage, clock });
  gate.startCooldown();
  assert.equal(gate.cooldownRemainingMs(), 600000);
  let sent = false;
  await assert.rejects(
    gate.run(async () => {
      sent = true;
    }),
    ChatRateLimitedError,
  );
  assert.equal(sent, false);
  gate.clearCooldown();
  assert.equal(await gate.run(async () => 'ok'), 'ok');
});
