// ============================================================
// CACHE — simple in-memory Map with per-entry TTL
// Best practice for SPA: avoid stale data by using short TTLs.
// IndexedDB not needed at this scale.
// ============================================================

class Cache {
  constructor() {
    this._store = new Map();
  }

  /** Store value with TTL in milliseconds */
  set(key, value, ttlMs = 120_000) {
    this._store.set(key, {
      value,
      expiresAt: Date.now() + ttlMs,
    });
  }

  /** Retrieve value, returns null if missing or expired */
  get(key) {
    const entry = this._store.get(key);
    if (!entry) return null;
    if (Date.now() > entry.expiresAt) {
      this._store.delete(key);
      return null;
    }
    return entry.value;
  }

  /** Remove a specific key */
  invalidate(key) {
    this._store.delete(key);
  }

  /** Remove all keys matching a prefix */
  invalidatePrefix(prefix) {
    for (const key of this._store.keys()) {
      if (key.startsWith(prefix)) this._store.delete(key);
    }
  }

  /** Clear everything */
  clear() {
    this._store.clear();
  }
}

export const cache = new Cache();
