import { createStorageResponse, isStorageRequest } from '../shared/storage_messages.js';

/** Answers storage requests posted by the page in the same window. */
export function startStorageHost({ window, storageArea }) {
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
