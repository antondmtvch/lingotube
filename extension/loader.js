// Classic content script (ISOLATED world). It only serves the storage bridge: it
// answers the page's chrome.storage requests. The page bundle (src/page/bundle.js,
// generated from src/page/main.js by scripts/build-page-bundle.mjs) is declared in
// manifest.json as a separate MAIN-world content script, so this file does not load it.
// A classic content script cannot import extension modules, so the storage host is
// plain code here.

// --- Duplicated from src/shared/storage_messages.js (canonical copy). ---
// tests/loader_parity.test.js fails if this block drifts from that module.
const STORAGE_CHANNEL = 'lingotube-storage';

const STORAGE_OPERATIONS = ['get', 'set', 'remove'];

function isStorageRequest(data) {
  return (
    typeof data === 'object' &&
    data !== null &&
    data.channel === STORAGE_CHANNEL &&
    data.kind === 'request' &&
    typeof data.requestId === 'number' &&
    STORAGE_OPERATIONS.includes(data.operation)
  );
}

/** Builds the answer: either a result or an error text. */
function createStorageResponse(requestId, result, errorText) {
  return { channel: STORAGE_CHANNEL, kind: 'response', requestId, result, errorText };
}

// --- Duplicated from src/content/storage_host.js (tested implementation). ---
/** Answers storage requests posted by the page in the same window. */
function startStorageHost({ window, storageArea }) {
  async function runOperation(operation, payload) {
    if (operation === 'get') return (await storageArea.get(payload.keys)) ?? {};
    if (operation === 'set') await storageArea.set(payload.items);
    if (operation === 'remove') await storageArea.remove(payload.keys);
    return {};
  }

  window.addEventListener('message', async (event) => {
    if (event.source !== window || !isStorageRequest(event.data)) return;
    const { requestId, operation, payload } = event.data;
    let response;
    try {
      response = createStorageResponse(requestId, await runOperation(operation, payload ?? {}), null);
    } catch (error) {
      response = createStorageResponse(requestId, null, String(error?.message ?? error));
    }
    window.postMessage(response, '*');
  });
}

try {
  startStorageHost({ window, storageArea: chrome.storage.local });
} catch {
  console.error('lingotube: storage host did not start');
}
