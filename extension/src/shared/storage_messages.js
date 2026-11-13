export const STORAGE_CHANNEL = 'lingotube-storage';

const STORAGE_OPERATIONS = ['get', 'set', 'remove'];

/** Builds a request that the page sends to the storage host. */
export function createStorageRequest(requestId, operation, payload) {
  return { channel: STORAGE_CHANNEL, kind: 'request', requestId, operation, payload };
}

export function isStorageRequest(data) {
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
export function createStorageResponse(requestId, result, errorText) {
  return { channel: STORAGE_CHANNEL, kind: 'response', requestId, result, errorText };
}

export function isStorageResponse(data) {
  return (
    typeof data === 'object' &&
    data !== null &&
    data.channel === STORAGE_CHANNEL &&
    data.kind === 'response' &&
    typeof data.requestId === 'number'
  );
}
