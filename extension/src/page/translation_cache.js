const CACHE_INDEX_KEY = 'cacheIndex';
const DEFAULT_MAX_TOTAL_BYTES = 4000000;

function isPlainObject(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** A caption translation entry: `translations` is an object holding only strings. */
function isTranslationsEntry(value) {
  return isPlainObject(value)
    && isPlainObject(value.translations)
    && Object.values(value.translations).every((text) => typeof text === 'string');
}

function isTimedLine(line) {
  return isPlainObject(line) && Number.isFinite(line.startMs) && Number.isFinite(line.endMs)
    && typeof line.text === 'string';
}

/** A chat transcript entry: `chunks` maps chunk indexes to lists of {startMs, endMs, text}. */
function isChunksEntry(value) {
  return isPlainObject(value)
    && isPlainObject(value.chunks)
    && Object.entries(value.chunks).every(
      ([index, lines]) => /^\d+$/.test(index) && Array.isArray(lines) && lines.every(isTimedLine),
    );
}

function isWellFormedEntry(value) {
  return isTranslationsEntry(value) || isChunksEntry(value);
}

function isIndexItem(item) {
  return isPlainObject(item) && typeof item.key === 'string'
    && Number.isFinite(item.savedAtMs) && Number.isFinite(item.bytes);
}

/**
 * Bounded cache of translations in the extension storage. Storage failures never
 * reach the caller: subtitles keep working without the cache.
 */
export class TranslationCache {
  /**
   * @param {{get: Function, set: Function, remove: Function}} extensionStorage
   * @param {{maxTotalBytes?: number, now?: () => number}} [options]
   */
  #saveQueue = Promise.resolve();

  constructor(extensionStorage, { maxTotalBytes = DEFAULT_MAX_TOTAL_BYTES, now = () => Date.now() } = {}) {
    this.extensionStorage = extensionStorage;
    this.maxTotalBytes = maxTotalBytes;
    this.now = now;
  }

  /**
   * @param {string} key
   * @returns {Promise<object|null>} a {translations} or {chunks} entry; null when missing, malformed or unreadable
   */
  async load(key) {
    try {
      const stored = await this.extensionStorage.get([key]);
      return isWellFormedEntry(stored[key]) ? stored[key] : null;
    } catch {
      return null;
    }
  }

  /**
   * Stores the entry, evicting the oldest ones until the total fits. Resolves even on failure.
   * @param {string} key
   * @param {object} entry a {translations} or {chunks} entry
   * @returns {Promise<void>}
   */
  save(key, entry) {
    // Saves read-modify-write the shared index, so they run one after another.
    const result = this.#saveQueue.then(() => this.#saveNow(key, entry));
    this.#saveQueue = result;
    return result;
  }

  async #saveNow(key, entry) {
    try {
      if (!isWellFormedEntry(entry)) return;
      const bytes = JSON.stringify(entry).length;
      if (bytes > this.maxTotalBytes) return;

      const stored = await this.extensionStorage.get([CACHE_INDEX_KEY]);
      const rawIndex = stored[CACHE_INDEX_KEY];
      const index = (Array.isArray(rawIndex) ? rawIndex.filter(isIndexItem) : [])
        .filter((item) => item.key !== key)
        .sort((first, second) => first.savedAtMs - second.savedAtMs);

      let totalBytes = bytes + index.reduce((sum, item) => sum + item.bytes, 0);
      const evictedKeys = [];
      while (totalBytes > this.maxTotalBytes && index.length > 0) {
        const oldest = index.shift();
        totalBytes -= oldest.bytes;
        evictedKeys.push(oldest.key);
      }

      if (evictedKeys.length > 0) await this.extensionStorage.remove(evictedKeys);
      index.push({ key, savedAtMs: this.now(), bytes });
      await this.extensionStorage.set({ [key]: entry, [CACHE_INDEX_KEY]: index });
    } catch {
      // The cache is an optimisation only; a full or silent storage must not break subtitles.
    }
  }
}
