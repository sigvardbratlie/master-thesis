// ============================================================
// GLOBAL STATUS PANEL — background pipeline progress log
// ============================================================

import { mapStatusEvent } from './status_mapper.js';

const PANEL_ID = 'global-pipeline-status';

let _isVisible = false;

function _ensurePanel() {
  if (document.getElementById(PANEL_ID)) return;

  const el = document.createElement('div');
  el.id = PANEL_ID;
  el.className = 'hidden fixed bottom-4 right-4 z-[1000] w-full max-w-sm';
  el.innerHTML = `
    <div class="bg-surface-container-high rounded-2xl shadow-2xl ring-1 ring-outline-variant/10 overflow-hidden">
      <!-- Header -->
      <div class="flex items-center gap-2 px-4 py-3 border-b border-outline-variant/10">
        <span id="gps-spinner" class="w-2.5 h-2.5 rounded-full bg-secondary animate-pulse flex-shrink-0"></span>
        <span id="gps-title" class="flex-1 text-sm font-bold text-on-surface truncate">Processing…</span>
        <button id="gps-close" class="p-1 rounded-lg hover:bg-surface-container transition-colors">
          <span class="material-symbols-outlined text-[16px] text-on-surface-variant">close</span>
        </button>
      </div>
      <!-- Hint -->
      <div class="px-4 py-2 bg-secondary-container/20 border-b border-outline-variant/10">
        <p class="text-[11px] text-on-surface-variant">
          You can continue working — we'll notify you when done.
        </p>
      </div>
      <!-- Log -->
      <div id="gps-log"
        class="px-4 py-3 space-y-0.5 max-h-52 overflow-y-auto text-xs font-mono text-on-surface-variant">
      </div>
    </div>`;
  document.body.appendChild(el);
  document.getElementById('gps-close').addEventListener('click', hideGlobalStatus);
}

// ── Public API ───────────────────────────────────────────────

/**
 * Shows the panel (preserves existing log content).
 */
export function showGlobalStatus() {
  _ensurePanel();
  document.getElementById(PANEL_ID)?.classList.remove('hidden');
  _isVisible = true;
}

/**
 * Hides the panel.
 */
export function hideGlobalStatus() {
  document.getElementById(PANEL_ID)?.classList.add('hidden');
  _isVisible = false;
}

/**
 * Opens the panel with a fresh log and a given title.
 * @param {string} [title]
 */
export function startGlobalStatusLog(title = 'Processing…') {
  _ensurePanel();
  document.getElementById(PANEL_ID)?.classList.remove('hidden');
  _isVisible = true;

  const titleEl   = document.getElementById('gps-title');
  const spinnerEl = document.getElementById('gps-spinner');
  const logEl     = document.getElementById('gps-log');

  if (titleEl)   titleEl.textContent = title;
  if (spinnerEl) spinnerEl.className = 'w-2.5 h-2.5 rounded-full bg-secondary animate-pulse flex-shrink-0';
  if (logEl)     logEl.innerHTML = '';
}

/**
 * Appends a status event as a log line.
 * @param {import('./status_mapper.js').StatusEvent} event
 */
export function addGlobalStatusLogLine(event) {
  if (!_isVisible) return;
  const { icon, message, details } = mapStatusEvent(event);
  const logEl = document.getElementById('gps-log');
  if (!logEl) return;

  const p = document.createElement('p');
  p.textContent = `${icon} ${message}`;
  logEl.appendChild(p);

  if (details) {
    const d = document.createElement('p');
    d.textContent = details;
    d.className = 'text-[10px] text-on-surface-variant/60 pl-5 -mt-0.5 mb-0.5';
    logEl.appendChild(d);
  }
  logEl.scrollTop = logEl.scrollHeight;
}

/**
 * Kept for backwards compatibility — delegates to addGlobalStatusLogLine.
 * @param {import('./status_mapper.js').StatusEvent} event
 */
export function updateGlobalStatus(event) {
  addGlobalStatusLogLine(event);
}

/**
 * Updates the panel header to show completion.
 * @param {string} [message]
 */
export function setGlobalStatusComplete(message = '✅ Process complete!') {
  const titleEl   = document.getElementById('gps-title');
  const spinnerEl = document.getElementById('gps-spinner');
  const logEl     = document.getElementById('gps-log');

  if (titleEl)   titleEl.textContent = message;
  if (spinnerEl) spinnerEl.className = 'w-2.5 h-2.5 rounded-full bg-secondary flex-shrink-0';
  if (logEl) {
    const p = document.createElement('p');
    p.textContent = message;
    p.className = 'font-semibold text-secondary mt-1';
    logEl.appendChild(p);
    logEl.scrollTop = logEl.scrollHeight;
  }
}

/**
 * Updates the panel header to show an error.
 * @param {string} errorMessage
 */
export function setGlobalStatusError(errorMessage) {
  const titleEl   = document.getElementById('gps-title');
  const spinnerEl = document.getElementById('gps-spinner');
  const logEl     = document.getElementById('gps-log');

  if (titleEl)   titleEl.textContent = '❌ Error';
  if (spinnerEl) spinnerEl.className = 'w-2.5 h-2.5 rounded-full bg-error flex-shrink-0';
  if (logEl) {
    const p = document.createElement('p');
    p.textContent = `❌ ${errorMessage}`;
    p.className = 'text-error font-semibold mt-1';
    logEl.appendChild(p);
    logEl.scrollTop = logEl.scrollHeight;
  }
}
