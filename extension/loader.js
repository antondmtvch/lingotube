// Classic content script (ISOLATED world). A classic content script cannot
// import extension modules, so the storage host is plain code here and then
// the page code is injected into the MAIN world as one classic script tag: src/page/bundle.js,
// generated from src/page/main.js by scripts/build-page-bundle.mjs.

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

  // A classic script: Chrome refuses to load an extension module script from the page.
  const pageScript = document.createElement('script');
  pageScript.src = chrome.runtime.getURL('src/page/bundle.js');
  document.documentElement.appendChild(pageScript);
} catch {
  console.error('lingotube: page module did not start');
}
