// ============================================================
// UTILS — shared helpers
// ============================================================

/** Format ISO date string to readable short date */
export function formatDate(iso, opts = { day: 'numeric', month: 'short', year: 'numeric' }) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('no-NO', opts);
}

/** Format ISO date string to readable date + time (e.g. "10. apr. 2026, 14:32") */
export function formatDateTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('no-NO', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/** Format ISO date to relative time (e.g. "2 timer siden") */
export function timeAgo(iso) {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const mins  = Math.floor(diff / 60_000);
  if (mins < 1)   return 'Nettopp';
  if (mins < 60)  return `${mins} min siden`;
  const hrs = Math.floor(mins / 60);
  if (hrs  < 24)  return `${hrs} t siden`;
  const days = Math.floor(hrs / 24);
  if (days < 7)   return `${days} dager siden`;
  return formatDate(iso);
}

/** Get initials from a name string */
export function initials(name = '') {
  return name.trim().split(/\s+/).map(p => p[0]).join('').toUpperCase().slice(0, 2);
}

/** Escape HTML entities */
export function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Map a filename extension to a backend-accepted MIME type (FileType enum). */
const _EXT_MIME = {
  pdf:  'application/pdf',
  txt:  'text/plain',
  csv:  'text/csv',
  md:   'text/markdown',
  eml:  'message/rfc822',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
};

export function resolveFileType(file) {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  return _EXT_MIME[ext] ?? file.type ?? 'text/plain';
}

/**
 * Convert an ArrayBuffer to a base64 string.
 * Uses chunked processing to avoid "Maximum call stack size exceeded"
 * when spreading large Uint8Arrays into String.fromCharCode.
 */
export function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary  = '';
  const chunk = 8192;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

/** Generate a UUID v4 */
export function uuid() {
  return crypto.randomUUID();
}

/** Format currency */
export function formatCurrency(amount, currency = 'NOK') {
  if (amount == null) return '—';
  return new Intl.NumberFormat('no-NO', { style: 'currency', currency }).format(amount);
}

/** Show a transient toast notification */
export function toast(message, type = 'info') {
  const colors = {
    info:    'bg-secondary text-white',
    success: 'bg-green-600 text-white',
    error:   'bg-error text-white',
    warning: 'bg-tertiary-fixed-dim text-on-surface',
  };
  const el = document.createElement('div');
  el.className = `fixed bottom-6 right-6 z-[9999] px-5 py-3 rounded-xl shadow-xl text-sm font-semibold font-body transition-all duration-300 ${colors[type] ?? colors.info}`;
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 300);
  }, 3000);
}

/** Render a loading skeleton block */
export function skeleton(rows = 3) {
  return Array.from({ length: rows }, () =>
    `<div class="h-4 bg-surface-container-high rounded animate-pulse mb-2"></div>`
  ).join('');
}

/** Convert markdown-like bold/italic to HTML (minimal subset for AI responses) */
export function simpleMarkdown(text) {
  return escHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code class="bg-surface-container px-1 rounded text-xs">$1</code>')
    .replace(/\n/g, '<br>');
}
