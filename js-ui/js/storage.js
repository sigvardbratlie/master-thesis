// ============================================================
// STORAGE — reads attachments from GCS via FastAPI backend
//
// Backend proxies all file access using the server-side service
// account key (gcloud-keys.json). The key NEVER reaches the browser.
//
// Flow:
//   JS → GET /storage/file?path=...&content_type=...  (Bearer token)
//      ← streaming bytes with correct Content-Type
//   JS → URL.createObjectURL(blob) → <iframe> / <pre>
// ============================================================

import { authService } from './auth.js';
import { CONFIG }      from './config.js';
import { apiLog }      from './logger.js';
import { cache }       from './cache.js';

const FILE_URL_TTL = 55 * 60 * 1000; // 55 min

/**
 * Fetch a GCS file via the backend proxy and return a blob object URL.
 * The URL is cached for 55 minutes to avoid redundant requests.
 * Caller must NOT revoke the URL if caching is desired; call revokeFileObjectUrl() on close.
 */
export async function fetchFileAsObjectUrl(path, contentType = 'application/pdf') {
  const cacheKey = `file-url:${path}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const token = await authService.getAccessToken();
  const res = await fetch(
    `${CONFIG.backendUrl}/storage/file?path=${encodeURIComponent(path)}&content_type=${encodeURIComponent(contentType)}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!res.ok) throw new Error(`File fetch failed: ${res.status} ${res.statusText}`);

  const blob = await res.blob();
  const url  = URL.createObjectURL(blob);
  cache.set(cacheKey, url, FILE_URL_TTL);
  apiLog.debug({ path, contentType }, 'File object URL created');
  return url;
}

/**
 * Fetch a GCS text file (txt, md, csv, …) as a string.
 * Not cached — text files are small and may be re-fetched cheaply.
 */
export async function fetchTextFile(path) {
  const token = await authService.getAccessToken();
  const res = await fetch(
    `${CONFIG.backendUrl}/storage/file?path=${encodeURIComponent(path)}&content_type=${encodeURIComponent('text/plain')}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!res.ok) throw new Error(`Text file fetch failed: ${res.status} ${res.statusText}`);
  return res.text();
}
