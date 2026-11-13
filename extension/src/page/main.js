import { createExtensionStorage } from './extension_storage.js';

async function checkStorageRoundTrip() {
  const extensionStorage = createExtensionStorage({ window });
  try {
    await extensionStorage.set({ 'lingotube:probe': 'ok' });
    const stored = await extensionStorage.get(['lingotube:probe']);
    await extensionStorage.remove(['lingotube:probe']);
    console.info(
      stored['lingotube:probe'] === 'ok'
        ? 'lingotube: page ready, storage ok'
        : 'lingotube: page ready, storage failed',
    );
  } catch (error) {
    console.info('lingotube: page ready, storage failed', error);
  }
}

checkStorageRoundTrip();
