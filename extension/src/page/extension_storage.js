import { createStorageRequest, isStorageResponse } from '../shared/storage_messages.js';

/** Storage client for the MAIN world: talks to the storage host by window messages. */
export function createExtensionStorage({ window, timeoutMs = 3000 }) {
  let lastRequestId = 0;

  function sendRequest(operation, payload) {
    const requestId = ++lastRequestId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        window.removeEventListener('message', onMessage);
        reject(new Error('extension storage did not answer'));
      }, timeoutMs);

      function onMessage(event) {
        if (event.source !== window || !isStorageResponse(event.data)) return;
        if (event.data.requestId !== requestId) return;
        clearTimeout(timer);
        window.removeEventListener('message', onMessage);
        if (event.data.errorText) reject(new Error(event.data.errorText));
        else resolve(event.data.result);
      }

      window.addEventListener('message', onMessage);
      window.postMessage(createStorageRequest(requestId, operation, payload), '*');
    });
  }

  return {
    get: (keys) => sendRequest('get', { keys }),
    set: async (items) => {
      await sendRequest('set', { items });
    },
    remove: async (keys) => {
      await sendRequest('remove', { keys });
    },
  };
}
