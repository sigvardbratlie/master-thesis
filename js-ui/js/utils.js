// ============================================================
// UTILS — shared helpers
// ============================================================

/** Format ISO date string to readable short date */
export function formatDate(iso, opts = { day: 'numeric', month: 'short', year: 'numeric' }) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('no-NO', opts);
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
