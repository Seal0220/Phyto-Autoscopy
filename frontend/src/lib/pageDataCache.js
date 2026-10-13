export const PAGE_CACHE_MAX_AGE_MS = 30_000;
export const PAGE_CACHE_INVALIDATED_EVENT = "phyto:page-cache-invalidated";

export function createPageDataCache({
  maxEntries = 16,
  now = Date.now,
} = {}) {
  const entries = new Map();
  let version = 0;
  return {
    get version() { return version; },
    read(key, maxAge = PAGE_CACHE_MAX_AGE_MS) {
      const entry = entries.get(key);
      if (!entry) return null;
      entries.delete(key);
      entries.set(key, entry);
      return { value: entry.value, fresh: now() - entry.updatedAt < maxAge };
    },
    write(key, value, expectedVersion = version) {
      if (expectedVersion !== version) return false;
      entries.delete(key);
      entries.set(key, { value: structuredClone(value), updatedAt: now() });
      while (entries.size > maxEntries) entries.delete(entries.keys().next().value);
      return true;
    },
    update(key, transform) {
      const entry = entries.get(key);
      if (entry) entry.value = transform(entry.value);
    },
    invalidate(prefix = "", { discard = false } = {}) {
      version += 1;
      for (const [key, entry] of entries) {
        if (!key.startsWith(prefix)) continue;
        if (discard) entries.delete(key);
        else entry.updatedAt = -Infinity;
      }
    },
    clear() {
      version += 1;
      entries.clear();
    },
  };
}

export function invalidatePageData(
  prefix = "",
  { discard = true } = {},
) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(PAGE_CACHE_INVALIDATED_EVENT, { detail: { prefix, discard } }));
}
