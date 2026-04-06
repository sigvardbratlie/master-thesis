// ============================================================
// STORAGE — leser vedlegg fra GCS via FastAPI backend
//
// Speil av: ui/src/ui/ui_components/attachments.py → read_attachment()
//           ui/src/ui/services/database_service.py  → read_attachment()
//
// GCS-nøkkelen (gcloud-keys.json) må ALDRI sendes til browser —
// den ligger på serveren og brukes av FastAPI til å generere
// signed URLs (tidsbegrensede, sikre nedlastingslenker).
//
// Flow:
//   JS → POST /storage/signed-url  (sender path)
//      ← { url: "https://storage.googleapis.com/..." }
//   JS → GET signed URL            (laster fil direkte fra GCS)
// ============================================================

import { authService } from './auth.js';
import { CONFIG }      from './config.js';
import { apiLog }      from './logger.js';
import { cache }       from './cache.js';

const SIGNED_URL_TTL = 55 * 60 * 1000; // 55 min (GCS signed URLs er typisk 60 min)

/**
 * Hent en signed URL for en GCS-fil.
 * Signed URL er midlertidig og kan brukes direkte i <iframe>/<img>/fetch.
 */
export async function getSignedUrl(path, contentType = 'application/pdf') {
  const cacheKey = `signed-url:${path}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const token = await authService.getAccessToken();
  const res = await fetch(`${CONFIG.backendUrl}/storage/signed-url`, {
    method:  'POST',
    headers: {
      'Content-Type':  'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ path, content_type: contentType }),
  });

  if (!res.ok) throw new Error(`signed-url feilet: ${res.status}`);
  const { url } = await res.json();
  cache.set(cacheKey, url, SIGNED_URL_TTL);
  apiLog.debug({ path, contentType }, 'Signed URL hentet');
  return url;
}

/**
 * Last ned vedlegg som Blob.
 * Brukes for å vise PDF i <iframe> eller laste ned filer.
 */
export async function downloadAttachment(path) {
  const url = await getSignedUrl(path);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`GCS nedlasting feilet: ${res.status}`);
  return res.blob();
}

/**
 * Lag en object URL for visning i <iframe> eller <img>.
 * Husk å kalle URL.revokeObjectURL(url) når du er ferdig.
 */
export async function getAttachmentObjectUrl(path) {
  const blob = await downloadAttachment(path);
  return URL.createObjectURL(blob);
}
