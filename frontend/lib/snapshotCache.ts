import {BoundedReadCache} from './boundedReadCache.ts';

type SnapshotMap = Record<string, unknown | null>;

/** Public database snapshots only; no session data or stale-on-error fallback. */
export function createSnapshotCache(
  readOne: (key: string) => Promise<unknown | null>,
  readMany: (keys: string[]) => Promise<SnapshotMap>,
  clock = Date.now,
) {
  const cache = new BoundedReadCache<unknown>({
    maxEntries: 64, maxBytes: 16 * 1024 * 1024,
    maxEntryBytes: 4 * 1024 * 1024, maxPending: 18,
  }, clock);
  return {
    async snapshot<T = Record<string, unknown>>(key: string): Promise<T | null> {
      return await cache.read(JSON.stringify(['one', key]), 60_000, () => readOne(key)) as T | null;
    },
    async snapshots<T = Record<string, unknown>>(keys: string[]): Promise<Record<string, T | null>> {
      // Keep each batch as one database read. Never assemble a batch from entries
      // captured at different times. Copy before awaiting so callers cannot alter it.
      const normalized = [...new Set(keys)].sort();
      if (!normalized.length) return {};
      return await cache.read(JSON.stringify(['many', normalized]), 60_000,
        () => readMany(normalized)) as Record<string, T | null>;
    },
  };
}
