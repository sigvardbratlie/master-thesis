// ============================================================
// POPOVERS — standalone entity detail modals, fully editable
// Types: event, party, claim, deadline, damage
//
// Usage:
//   import { initPopovers, registerItems, openPopover } from '../components/popovers.js';
//   initPopovers();
//   registerItems('event', eventsArray, 'event_id');
//   openPopover('event', someEventId);
// ============================================================

import { escHtml, formatDate, formatCurrency, toast } from '../utils.js';
import { authService } from '../auth.js';
import {
  updateProjectEvent,
  updateProjectClaim,
  updateProjectDeadline,
  updateProjectDamage,
  updateProjectParty,
  deleteProjectEvent,
  deleteProjectParty,
  deleteProjectClaim,
  deleteProjectDeadline,
  deleteProjectDamage,
} from '../api.js';

// ── State ────────────────────────────────────────────────────
let _bound       = false;
let _currentType = null;
let _currentData = null;
let _editMode    = false;
const _stores = {
  event:    new Map(),
  party:    new Map(),
  claim:    new Map(),
  deadline: new Map(),
  damage:   new Map(),
};

// ── Public API ───────────────────────────────────────────────

export function initPopovers() {
  if (document.getElementById('entity-popover')) return;
  const div = document.createElement('div');
  div.innerHTML = _shell();
  document.body.appendChild(div.firstElementChild);
  _bindEvents();
}

export function registerItems(type, items, idKey) {
  if (!_stores[type]) return;
  // Merge: incoming items from cache may be stale vs. an in-session save,
  // so only replace an entry if we don't already have a locally-saved copy
  // (indicated by updated_at being more recent than what's incoming).
  items.forEach(item => {
    const existing = _stores[type].get(item[idKey]);
    if (existing && existing._savedLocally) return; // keep the locally-saved version
    _stores[type].set(item[idKey], item);
  });
  // Remove entries that no longer exist in the incoming set
  const incomingIds = new Set(items.map(i => i[idKey]));
  for (const [k, v] of _stores[type]) {
    if (!incomingIds.has(k) && !v._savedLocally) _stores[type].delete(k);
  }
}

export function openPopover(type, id) {
  const data  = _stores[type]?.get(id);
  const modal = document.getElementById('entity-popover');
  if (!data || !modal) return;

  _currentType = type;
  _currentData = data;
  _editMode    = false;

  document.getElementById('entity-popover-inner').innerHTML = _render(type, data);
  modal.classList.remove('hidden');

  requestAnimationFrame(() => {
    const panel = document.getElementById('entity-popover-panel');
    if (panel) {
      panel.style.opacity   = '1';
      panel.style.transform = 'scale(1) translateY(0)';
    }
  });
}

export function closePopover() {
  const modal = document.getElementById('entity-popover');
  const panel = document.getElementById('entity-popover-panel');
  if (!modal) return;
  if (panel) {
    panel.style.opacity   = '0';
    panel.style.transform = 'scale(0.97) translateY(8px)';
    setTimeout(() => {
      modal.classList.add('hidden');
      _editMode = false;
    }, 180);
  } else {
    modal.classList.add('hidden');
    _editMode = false;
  }
}

// ── Shell ────────────────────────────────────────────────────

function _shell() {
  return `
    <div id="entity-popover"
         class="hidden fixed inset-0 z-[150] flex items-center justify-center p-4 sm:p-6 md:p-8">
      <div id="entity-popover-backdrop"
           class="absolute inset-0 bg-on-surface/25 backdrop-blur-sm"></div>
      <div id="entity-popover-panel"
           class="relative w-full max-w-3xl flex flex-col rounded-xl max-h-[90vh]
                  shadow-[0_32px_80px_-8px_rgba(8,25,66,0.20)] border border-white/40 overflow-hidden"
           style="opacity:0; transform:scale(0.97) translateY(8px);
                  transition:opacity 0.18s ease, transform 0.18s ease;
                  background:rgba(252,249,247,0.94);
                  backdrop-filter:blur(24px); -webkit-backdrop-filter:blur(24px);">
        <div id="entity-popover-inner" class="flex flex-col min-h-0 flex-1"></div>
      </div>
    </div>`;
}

// ── Event binding ────────────────────────────────────────────

function _bindEvents() {
  if (_bound) return;
  _bound = true;

  document.addEventListener('click', async (e) => {
    if (e.target.closest('#entity-popover-backdrop'))  { closePopover(); return; }
    if (e.target.closest('[data-close-popover]'))       { closePopover(); return; }
    if (e.target.closest('[data-enter-edit]'))          { _enterEditMode(); return; }
    if (e.target.closest('[data-cancel-edit]'))         { _exitEditMode(); return; }
    if (e.target.closest('[data-save-edit]'))           { await _handleSave(); return; }
    if (e.target.closest('[data-delete-entity]'))       { _swapFooter(true); return; }
    if (e.target.closest('[data-cancel-delete]'))       { _swapFooter(false); return; }
    if (e.target.closest('[data-confirm-delete]'))      { await _handleDelete(); return; }
    const srcBtn = e.target.closest('[data-source-type]');
    if (srcBtn) {
      document.dispatchEvent(new CustomEvent('open-source', {
        detail: { type: srcBtn.dataset.sourceType, id: srcBtn.dataset.sourceId },
      }));
      return;
    }

    const item = e.target.closest('.popover-item');
    if (item) openPopover(item.dataset.popoverType, item.dataset.popoverId);
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (_editMode) _exitEditMode();
      else closePopover();
    }
  });
}

// ── Mode helpers ─────────────────────────────────────────────

function _enterEditMode() {
  _editMode = true;
  document.getElementById('entity-popover-inner').innerHTML =
    _renderEdit(_currentType, _currentData);
}

function _exitEditMode() {
  _editMode = false;
  document.getElementById('entity-popover-inner').innerHTML =
    _render(_currentType, _currentData);
}

// ── Delete handler ────────────────────────────────────────────

function _swapFooter(confirmMode) {
  const existing = document.getElementById('popover-footer');
  if (!existing) return;
  const tmp = document.createElement('div');
  tmp.innerHTML = confirmMode ? _deleteConfirmFooter() : _footer(_sourceLink(_currentData));
  existing.replaceWith(tmp.firstElementChild);
}

async function _handleDelete() {
  const idKey     = _idKey(_currentType);
  const entityId  = _currentData[idKey];
  const projectId = _currentData.project_id ?? null;

  const btn = document.querySelector('[data-confirm-delete]');
  if (btn) { btn.disabled = true; btn.textContent = 'Deleting…'; }

  try {
    switch (_currentType) {
      case 'event':    await deleteProjectEvent(entityId, projectId);    break;
      case 'party':    await deleteProjectParty(entityId, projectId);    break;
      case 'claim':    await deleteProjectClaim(entityId, projectId);    break;
      case 'deadline': await deleteProjectDeadline(entityId, projectId); break;
      case 'damage':   await deleteProjectDamage(entityId, projectId);   break;
    }

    _stores[_currentType]?.delete(entityId);
    closePopover();

    const label = _currentType.charAt(0).toUpperCase() + _currentType.slice(1);
    toast(`${label} deleted`, 'success');

    document.dispatchEvent(new CustomEvent('entity-deleted', {
      detail: { type: _currentType, projectId },
    }));
  } catch (err) {
    toast(err.message, 'error');
    if (btn) { btn.disabled = false; btn.textContent = 'Delete'; }
    _swapFooter(false);
  }
}

// ── Save handler ─────────────────────────────────────────────

async function _handleSave() {
  const form = document.getElementById('entity-edit-form');
  if (!form) return;

  // Collect all named inputs/selects/textareas
  const raw = {};
  new FormData(form).forEach((v, k) => { raw[k] = v; });

  // Build update payload — convert empty strings to null
  const updates = {};
  for (const [k, v] of Object.entries(raw)) {
    updates[k] = v === '' ? null : v;
  }

  // Type-specific coercions
  switch (_currentType) {
    case 'event':
      updates.disputed = form.querySelector('#edit-disputed')?.checked ?? false;
      delete updates.disputed_checkbox; // guard
      if (updates.event_start_date) updates.event_start_date = new Date(updates.event_start_date + 'T00:00:00').toISOString();
      if (updates.event_end_date)   updates.event_end_date   = new Date(updates.event_end_date   + 'T00:00:00').toISOString();
      break;
    case 'deadline':
      if (updates.deadline_date) updates.deadline_date = new Date(updates.deadline_date + 'T00:00:00').toISOString();
      break;
    case 'damage':
      updates.amount = updates.amount !== null ? (parseFloat(updates.amount) || null) : null;
      if (raw.supporting_evidence != null) {
        updates.supporting_evidence = raw.supporting_evidence
          ? raw.supporting_evidence.split('\n').map(s => s.trim()).filter(Boolean)
          : null;
      }
      break;
  }

  // Get current user id
  let userId = null;
  try {
    const { data: { user } } = await authService.client.auth.getUser();
    userId = user?.id ?? null;
  } catch { /* best-effort */ }

  const projectId = _currentData.project_id ?? null;
  const idKey     = _idKey(_currentType);
  const entityId  = _currentData[idKey];

  // Visual: disable save button
  const saveBtn = document.querySelector('[data-save-edit]');
  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Saving…'; }

  try {
    let updated;
    switch (_currentType) {
      case 'event':    updated = await updateProjectEvent(entityId,    projectId, updates, userId); break;
      case 'claim':    updated = await updateProjectClaim(entityId,    projectId, updates, userId); break;
      case 'deadline': updated = await updateProjectDeadline(entityId, projectId, updates, userId); break;
      case 'damage':   updated = await updateProjectDamage(entityId,   projectId, updates, userId); break;
      case 'party':    updated = await updateProjectParty(entityId,    projectId, updates, userId); break;
    }

    // Merge — preserve joined data (e.g. project_party_reps) not returned by plain update.
    // _savedLocally flag prevents registerItems from overwriting with stale cache data.
    _currentData = { ..._currentData, ...updated, _savedLocally: true };
    _stores[_currentType]?.set(_currentData[idKey], _currentData);

    _editMode = false;
    document.getElementById('entity-popover-inner').innerHTML = _render(_currentType, _currentData);
    toast('Changes saved', 'success');
  } catch (err) {
    toast(err.message, 'error');
    if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Save'; }
  }
}

// ── Dispatchers ──────────────────────────────────────────────

function _render(type, data) {
  switch (type) {
    case 'event':    return _renderEvent(data);
    case 'party':    return _renderParty(data);
    case 'claim':    return _renderClaim(data);
    case 'deadline': return _renderDeadline(data);
    case 'damage':   return _renderDamage(data);
    default: return '';
  }
}

function _renderEdit(type, data) {
  switch (type) {
    case 'event':    return _renderEditEvent(data);
    case 'party':    return _renderEditParty(data);
    case 'claim':    return _renderEditClaim(data);
    case 'deadline': return _renderEditDeadline(data);
    case 'damage':   return _renderEditDamage(data);
    default: return '';
  }
}

// ── Shared helpers ───────────────────────────────────────────

function _idKey(type) {
  return { event: 'event_id', party: 'party_id', claim: 'claim_id', deadline: 'deadline_id', damage: 'damage_id' }[type];
}

function _sigBadge(sig) {
  const s = (sig ?? '').toLowerCase();
  if (s === 'high') return `
    <div class="inline-flex items-center gap-2 bg-error-container/40 px-3 py-1.5 rounded-full border border-error/10">
      <span class="w-2 h-2 rounded-full bg-error flex-shrink-0"></span>
      <span class="text-[10px] font-bold text-on-error-container uppercase tracking-tight">High Impact</span>
    </div>`;
  if (s === 'medium') return `
    <div class="inline-flex items-center gap-2 bg-tertiary-fixed/30 px-3 py-1.5 rounded-full border border-tertiary-fixed-dim/20">
      <span class="w-2 h-2 rounded-full bg-tertiary-fixed-dim flex-shrink-0"></span>
      <span class="text-[10px] font-bold text-on-tertiary-container uppercase tracking-tight">Medium Impact</span>
    </div>`;
  if (s === 'low') return `
    <div class="inline-flex items-center gap-2 bg-surface-container px-3 py-1.5 rounded-full border border-outline-variant/15">
      <span class="w-2 h-2 rounded-full bg-outline flex-shrink-0"></span>
      <span class="text-[10px] font-bold text-on-surface-variant uppercase tracking-tight">Low Impact</span>
    </div>`;
  return sig
    ? `<span class="text-xs font-medium text-on-surface-variant">${escHtml(sig)}</span>`
    : `<span class="text-[10px] text-on-surface-variant/40 italic">Not assessed</span>`;
}

function _strengthBars(assessment) {
  const s      = (assessment ?? '').toLowerCase();
  const filled = s.includes('strong') ? 3 : s.includes('moderate') ? 2 : s.includes('weak') ? 1 : 0;
  const bars   = Array.from({ length: 4 }, (_, i) =>
    `<div class="w-3 h-1.5 rounded-full ${i < filled ? 'bg-secondary' : 'bg-outline-variant'}"></div>`
  ).join('');
  return `<div class="flex gap-0.5">${bars}</div>`;
}

function _splitPoints(text) {
  if (!text) return [];
  return text.split(/(?<=\.)\s+(?=[A-Z])|\n+/).map(s => s.trim()).filter(Boolean);
}

function _daysRemaining(date) {
  const now = new Date(); now.setHours(0, 0, 0, 0);
  const d   = new Date(date); d.setHours(0, 0, 0, 0);
  return Math.round((d - now) / 86_400_000);
}

function _isoToDate(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  } catch { return ''; }
}

function _evidenceToText(evidence) {
  if (!evidence) return '';
  const arr = Array.isArray(evidence)
    ? evidence
    : (typeof evidence === 'object' ? Object.values(evidence) : [evidence]);
  return arr.map(e => (typeof e === 'string' ? e : JSON.stringify(e))).join('\n');
}

// ── View-mode UI primitives ──────────────────────────────────

function _closeBtn() {
  return `
    <button data-close-popover
            class="p-2 hover:bg-surface-container rounded-lg transition-colors text-on-surface-variant hover:text-on-surface flex-shrink-0"
            title="Close">
      <span class="material-symbols-outlined text-[22px]">close</span>
    </button>`;
}

function _headerActions() {
  return `
    <div class="flex items-center gap-1 flex-shrink-0">
      <button data-enter-edit
              class="p-2 hover:bg-surface-container rounded-lg transition-colors text-on-surface-variant hover:text-secondary"
              title="Edit">
        <span class="material-symbols-outlined text-[20px]">edit</span>
      </button>
      <button data-delete-entity
              class="p-2 hover:bg-error-container/30 rounded-lg transition-colors text-on-surface-variant/40 hover:text-error"
              title="Delete">
        <span class="material-symbols-outlined text-[20px]">delete</span>
      </button>
      ${_closeBtn()}
    </div>`;
}

function _sourceLink(data) {
  const hasEmail = !!data.email_id;
  const hasFile  = !!data.file_id;
  if (!hasEmail && !hasFile) return '';
  const icon = hasEmail ? 'mail' : 'description';
  const id   = escHtml(hasEmail ? data.email_id : data.file_id);
  return `
    <button class="flex items-center gap-1.5 text-xs font-semibold text-on-surface-variant/60
                   hover:text-secondary transition-colors group"
            data-source-type="${hasEmail ? 'email' : 'file'}" data-source-id="${id}">
      <span class="material-symbols-outlined text-[15px]">${icon}</span>
      <span>Source</span>
      <span class="material-symbols-outlined text-[13px] opacity-40 group-hover:opacity-100 transition-opacity">open_in_new</span>
    </button>`;
}

function _footer(source = '') {
  return `
    <div id="popover-footer" class="px-8 py-5 border-t border-outline-variant/10 flex items-center justify-between gap-3 flex-shrink-0"
         style="background:rgba(234,232,230,0.9);">
      <div>${source}</div>
      <button data-close-popover
              class="px-5 py-2 text-sm font-semibold text-on-surface-variant hover:text-on-surface transition-colors">
        Close
      </button>
    </div>`;
}

function _deleteConfirmFooter() {
  const label = _currentType
    ? _currentType.charAt(0).toUpperCase() + _currentType.slice(1)
    : 'item';
  return `
    <div id="popover-footer" class="px-8 py-4 border-t border-error/20 flex items-center justify-between gap-4 flex-shrink-0"
         style="background:rgba(254,242,242,0.95);">
      <div class="flex items-center gap-2 min-w-0">
        <span class="material-symbols-outlined text-[16px] text-error flex-shrink-0">warning</span>
        <span class="text-sm font-semibold text-error">Delete this ${label}? This cannot be undone.</span>
      </div>
      <div class="flex items-center gap-2 flex-shrink-0">
        <button data-cancel-delete
                class="px-4 py-1.5 text-sm font-semibold text-on-surface-variant hover:text-on-surface transition-colors rounded-lg">
          Cancel
        </button>
        <button data-confirm-delete
                class="px-5 py-2 bg-error text-on-error rounded-lg text-sm font-bold hover:opacity-90 transition-opacity">
          Delete
        </button>
      </div>
    </div>`;
}

function _metaStrip(data) {
  const parts = [];
  if (data.created_by || data.created_at) {
    const by   = data.created_by ? escHtml(data.created_by) : '';
    const when = data.created_at ? escHtml(formatDate(data.created_at)) : '';
    parts.push(`Created${by ? ` by ${by}` : ''}${when ? ` · ${when}` : ''}`);
  }
  if (data.updated_by || data.updated_at) {
    const by   = data.updated_by ? escHtml(data.updated_by) : '';
    const when = data.updated_at ? escHtml(formatDate(data.updated_at)) : '';
    parts.push(`Updated${by ? ` by ${by}` : ''}${when ? ` · ${when}` : ''}`);
  }
  if (!parts.length) return '';
  return `
    <div class="px-8 py-2.5 border-t border-outline-variant/8 flex flex-wrap gap-x-6 gap-y-0.5 flex-shrink-0"
         style="background:rgba(240,237,235,0.55);">
      ${parts.map(p => `<span class="text-[10px] text-on-surface-variant/35 font-mono">${p}</span>`).join('')}
    </div>`;
}

// ── Edit-mode UI primitives ──────────────────────────────────

const E = {
  input:    `w-full bg-surface-container-low border border-outline-variant/20 rounded-lg px-3 py-2 text-sm text-on-surface placeholder-on-surface-variant/30 focus:outline-none focus:ring-2 focus:ring-secondary/30 focus:border-secondary/40 transition-colors`,
  textarea: `w-full bg-surface-container-low border border-outline-variant/20 rounded-lg px-3 py-2 text-sm text-on-surface placeholder-on-surface-variant/30 focus:outline-none focus:ring-2 focus:ring-secondary/30 focus:border-secondary/40 transition-colors resize-none`,
  select:   `w-full bg-surface-container-low border border-outline-variant/20 rounded-lg px-3 py-2 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-secondary/30 focus:border-secondary/40 transition-colors`,
  label:    `text-[10px] font-black uppercase tracking-widest text-on-surface-variant/60 mb-1.5 block`,
};

function _fg(label, inputHtml) {
  return `<div><label class="${E.label}">${label}</label>${inputHtml}</div>`;
}

function _sigSelect(current) {
  const opts = ['high', 'medium', 'low'];
  return `
    <select name="significance" class="${E.select}">
      <option value="">— not set —</option>
      ${opts.map(o => `<option value="${o}" ${(current ?? '').toLowerCase() === o ? 'selected' : ''}>${o.charAt(0).toUpperCase() + o.slice(1)}</option>`).join('')}
    </select>`;
}

function _strengthSelect(current) {
  const opts = ['strong', 'moderate', 'weak'];
  return `
    <select name="strength_assessment" class="${E.select}">
      <option value="">— not set —</option>
      ${opts.map(o => `<option value="${o}" ${(current ?? '').toLowerCase() === o ? 'selected' : ''}>${o.charAt(0).toUpperCase() + o.slice(1)}</option>`).join('')}
    </select>`;
}

function _editHeader(iconHtml, titleText, idField, shortId) {
  return `
    <div class="px-8 py-5 border-b border-outline-variant/15 flex items-center justify-between flex-shrink-0"
         style="background:rgba(62,96,142,0.06);">
      <div class="flex items-center gap-4">
        ${iconHtml}
        <div>
          <div class="flex items-center gap-2">
            <h2 class="font-headline text-lg font-bold text-on-surface leading-tight">${escHtml(titleText)}</h2>
            <span class="text-[9px] font-black text-secondary bg-secondary/10 px-2 py-0.5 rounded-full uppercase tracking-widest">Editing</span>
          </div>
          <p class="text-[10px] text-on-surface-variant/50 font-mono mt-0.5">${escHtml(idField)}: ${escHtml(shortId)}</p>
        </div>
      </div>
      <div class="flex items-center gap-2 flex-shrink-0">
        <button data-cancel-edit type="button"
                class="px-4 py-1.5 text-sm font-semibold text-on-surface-variant hover:text-on-surface transition-colors">
          Cancel
        </button>
        <button data-save-edit type="button"
                class="px-5 py-2 bg-secondary text-on-secondary rounded-lg text-sm font-bold shadow-sm hover:opacity-90 transition-opacity">
          Save
        </button>
      </div>
    </div>`;
}

function _editFooter() {
  return `
    <div class="px-8 py-4 border-t border-outline-variant/10 flex justify-end gap-2 flex-shrink-0"
         style="background:rgba(234,232,230,0.9);">
      <button data-cancel-edit type="button"
              class="px-4 py-2 text-sm font-semibold text-on-surface-variant hover:text-on-surface transition-colors">
        Cancel
      </button>
      <button data-save-edit type="button"
              class="px-6 py-2 bg-secondary text-on-secondary rounded-lg text-sm font-bold shadow hover:opacity-90 transition-opacity">
        Save
      </button>
    </div>`;
}

// ────────────────────────────────────────────────────────────
// VIEW RENDERS
// ────────────────────────────────────────────────────────────

function _renderDeadline(d) {
  const title   = d.title ?? d.description ?? 'Deadline';
  const shortId = (d.deadline_id ?? '');
  const date    = d.deadline_date ? new Date(d.deadline_date) : null;
  const day     = date ? date.getDate() : '—';
  const month   = date ? date.toLocaleDateString('en-US', { month: 'short' }).toUpperCase() : '';
  const year    = date ? date.getFullYear() : '';
  const weekday = date ? date.toLocaleDateString('en-US', { weekday: 'long' }) : '—';
  const rem     = date ? _daysRemaining(date) : null;

  let remHtml = '';
  if (rem !== null) {
    const cls  = rem < 0 ? 'text-error' : rem <= 7 ? 'text-tertiary-fixed-dim' : 'text-secondary';
    const text = rem > 0 ? `${rem} day${rem !== 1 ? 's' : ''} remaining`
               : rem === 0 ? 'Due today'
               : `${Math.abs(rem)} day${Math.abs(rem) !== 1 ? 's' : ''} overdue`;
    remHtml = `<div class="mt-2 flex items-center gap-1.5 ${cls} text-xs font-semibold">
      <span class="material-symbols-outlined text-sm">schedule</span><span>${text}</span></div>`;
  }

  return `
    <div class="px-8 py-6 border-b border-outline-variant/15 flex items-center justify-between flex-shrink-0">
      <div class="flex items-center gap-4">
        <div class="w-12 h-12 bg-primary-container rounded-lg flex items-center justify-center flex-shrink-0">
          <span class="material-symbols-outlined text-3xl text-on-primary">alarm_on</span>
        </div>
        <div>
          <h2 class="font-headline text-xl font-bold text-on-surface leading-tight">${escHtml(title)}</h2>
          <p class="text-[10px] text-on-surface-variant/50 font-mono mt-0.5">deadline_id: ${escHtml(shortId)}</p>
        </div>
      </div>
      ${_headerActions()}
    </div>
    <div class="flex flex-col md:flex-row flex-1 min-h-0">
      <div class="w-full md:w-[44%] p-8 border-b md:border-b-0 md:border-r border-outline-variant/10 flex-shrink-0"
           style="background:rgba(246,243,241,0.6);">
        <div class="space-y-7">
          <div>
            <label class="text-[10px] font-black uppercase tracking-widest text-on-surface-variant/60 mb-4 block">Deadline Date</label>
            <div class="flex items-start gap-4">
              <div class="flex flex-col items-center bg-white border border-outline-variant/20 rounded-lg p-2 min-w-[60px] text-center shadow-sm flex-shrink-0">
                <span class="text-[10px] font-bold text-secondary uppercase tracking-tight">${escHtml(month)}</span>
                <span class="text-2xl font-black text-on-surface leading-none my-0.5">${day}</span>
                <span class="text-[10px] font-medium text-on-surface-variant/40">${year}</span>
              </div>
              <div class="flex-1 min-w-0">
                <p class="font-headline text-lg font-bold text-on-surface">${escHtml(weekday)}</p>
                ${d.party_role ? `<p class="text-xs text-on-surface-variant mt-0.5">${escHtml(d.party_role)}</p>` : ''}
                ${remHtml}
              </div>
            </div>
          </div>
          ${d.party_role ? `
          <div class="pt-6 border-t border-outline-variant/15">
            <label class="text-[10px] font-black uppercase tracking-widest text-on-surface-variant/60 mb-3 block">Responsible Party</label>
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 rounded-full bg-secondary-container flex items-center justify-center flex-shrink-0">
                <span class="material-symbols-outlined text-lg text-on-secondary-container">person</span>
              </div>
              <p class="text-sm font-bold text-on-surface">${escHtml(d.party_role)}</p>
            </div>
          </div>` : ''}
        </div>
      </div>
      <div class="w-full md:w-[56%] p-8 flex flex-col overflow-y-auto">
        <div class="mb-5">
          <label class="text-[10px] font-black uppercase tracking-widest text-on-surface-variant/60 mb-2 block">Criticality</label>
          ${_sigBadge(d.significance)}
        </div>
        <div class="flex-1">
          <label class="text-[10px] font-black uppercase tracking-widest text-on-surface-variant/60 mb-2 block">Description</label>
          <div class="bg-surface-container/30 rounded-xl p-5 border border-outline-variant/10">
            <p class="text-sm text-on-surface/90 leading-relaxed">${escHtml(d.description ?? 'No description recorded.')}</p>
          </div>
        </div>
      </div>
    </div>
    ${_metaStrip(d)}
    ${_footer(_sourceLink(d))}`;
}

function _renderClaim(c) {
  const title   = c.title ?? 'Claim';
  const shortId = (c.claim_id ?? '');
  const points  = _splitPoints(c.factual_basis);

  return `
    <div class="px-8 pt-8 pb-6 border-b border-outline-variant/10 flex-shrink-0">
      <div class="flex items-start justify-between gap-4">
        <div class="space-y-3 flex-1 min-w-0">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="bg-secondary/10 text-secondary px-3 py-1 rounded-full text-[10px] font-bold tracking-widest uppercase flex items-center gap-1.5 font-mono">
              <span class="material-symbols-outlined text-[12px]" style="font-variation-settings:'FILL' 1;">gavel</span>
              claim_id: ${escHtml(shortId)}
            </span>
            ${c.significance ? `<span class="bg-tertiary-fixed text-on-tertiary-fixed px-3 py-1 rounded-full text-[10px] font-bold tracking-widest uppercase">${escHtml(c.significance)}</span>` : ''}
            ${c.category ? `<span class="bg-surface-container text-on-surface-variant px-3 py-1 rounded-full text-[10px] font-bold tracking-widest uppercase">${escHtml(c.category)}</span>` : ''}
          </div>
          <h1 class="font-headline text-2xl font-extrabold text-primary tracking-tight leading-tight">${escHtml(title)}</h1>
          <div class="flex items-center flex-wrap gap-x-6 gap-y-1">
            ${c.party_role ? `<div class="flex items-center gap-2">
              <span class="text-[10px] text-outline font-medium uppercase tracking-wider">Party:</span>
              <span class="text-sm font-semibold text-on-surface">${escHtml(c.party_role)}</span>
            </div>` : ''}
            ${c.strength_assessment ? `<div class="flex items-center gap-2">
              <span class="text-[10px] text-outline font-medium uppercase tracking-wider">Strength:</span>
              <div class="flex items-center gap-1.5">
                ${_strengthBars(c.strength_assessment)}
                <span class="text-sm font-bold text-secondary capitalize">${escHtml(c.strength_assessment)}</span>
              </div>
            </div>` : ''}
          </div>
        </div>
        ${_headerActions()}
      </div>
    </div>
    <div class="flex-1 overflow-y-auto p-8 space-y-8 min-h-0">
      ${points.length ? `
      <section class="grid grid-cols-12 gap-6">
        <div class="col-span-3"><h2 class="text-[10px] font-bold text-outline uppercase tracking-[0.18em]">Factual Basis</h2></div>
        <div class="col-span-9"><ul class="space-y-3">
          ${points.map(pt => `<li class="flex gap-3 group">
            <span class="mt-2 w-1.5 h-1.5 rounded-full bg-secondary flex-shrink-0 group-hover:scale-125 transition-transform"></span>
            <p class="text-sm text-on-surface leading-relaxed">${escHtml(pt)}</p>
          </li>`).join('')}
        </ul></div>
      </section>` : ''}
      ${c.legal_basis ? `
      <section class="grid grid-cols-12 gap-6">
        <div class="col-span-3"><h2 class="text-[10px] font-bold text-outline uppercase tracking-[0.18em]">Legal Basis</h2></div>
        <div class="col-span-9">
          <div class="p-4 bg-surface-container-low rounded-lg border-l-2 border-secondary/30">
            <p class="text-sm text-on-surface leading-relaxed">${escHtml(c.legal_basis)}</p>
          </div>
        </div>
      </section>` : ''}
      ${c.defense ? `
      <section class="grid grid-cols-12 gap-6">
        <div class="col-span-3"><h2 class="text-[10px] font-bold text-outline uppercase tracking-[0.18em]">Defense</h2></div>
        <div class="col-span-9">
          <div class="p-4 bg-surface-container-low rounded-lg border-l-2 border-error/25">
            <p class="text-sm text-on-surface leading-relaxed">${escHtml(c.defense)}</p>
          </div>
        </div>
      </section>` : ''}
      ${c.relief_sought ? `
      <section class="grid grid-cols-12 gap-6">
        <div class="col-span-3"><h2 class="text-[10px] font-bold text-outline uppercase tracking-[0.18em]">Relief Sought</h2></div>
        <div class="col-span-9">
          <div class="bg-surface-container-lowest p-5 border border-outline-variant/10 rounded-xl relative overflow-hidden">
            <div class="absolute top-0 right-0 p-4 opacity-[0.04]"><span class="material-symbols-outlined text-6xl">payments</span></div>
            <p class="text-sm text-on-surface-variant leading-relaxed relative">${escHtml(c.relief_sought)}</p>
          </div>
        </div>
      </section>` : ''}
    </div>
    ${_metaStrip(c)}
    ${_footer(_sourceLink(c))}`;
}

function _renderEvent(ev) {
  const title   = ev.event_name ?? 'Event';
  const dateStr = ev.event_start_date ? formatDate(ev.event_start_date, { day: 'numeric', month: 'long', year: 'numeric' }) : '—';
  const endStr  = ev.event_end_date   ? ` – ${formatDate(ev.event_end_date, { day: 'numeric', month: 'long', year: 'numeric' })}` : '';
  const parties = Array.isArray(ev.parties) ? ev.parties : [];

  return `
    <div class="flex items-center justify-between px-7 py-5 border-b border-outline-variant/10 flex-shrink-0">
      <div>
        <h2 class="font-headline text-xl font-black tracking-tight text-primary uppercase">Event Details</h2>
        <p class="text-[10px] text-on-surface-variant/50 font-mono mt-0.5">event_id: ${escHtml((ev.event_id ?? ''))}</p>
      </div>
      ${_headerActions()}
    </div>
    <div class="p-8 space-y-7 flex-1 overflow-y-auto min-h-0">
      <div class="space-y-2">
        <div class="flex items-center gap-2 flex-wrap">
          ${ev.significance ? `<span class="bg-tertiary-fixed text-on-tertiary-fixed text-[10px] font-bold px-2.5 py-1 rounded-full tracking-widest uppercase">${escHtml(ev.significance)} Significance</span>` : ''}
          ${ev.category ? `<span class="bg-secondary-container text-on-secondary-container text-xs font-semibold px-3 py-1 rounded-full">${escHtml(ev.category)}</span>` : ''}
          ${ev.disputed ? `<span class="bg-error-container/40 text-error text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-tight">Disputed</span>` : ''}
        </div>
        <h3 class="font-headline text-2xl font-black text-primary-container leading-tight">${escHtml(title)}</h3>
        <div class="flex items-center gap-2 text-secondary">
          <span class="material-symbols-outlined text-sm">calendar_today</span>
          <span class="text-sm font-semibold">${escHtml(dateStr)}${escHtml(endStr)}</span>
        </div>
      </div>
      ${ev.description ? `
      <div class="space-y-2">
        <h4 class="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest">Description</h4>
        <div class="bg-surface-container-low p-5 rounded-lg border border-outline-variant/10">
          <p class="text-sm leading-relaxed text-on-surface">${escHtml(ev.description)}</p>
        </div>
      </div>` : ''}
      ${parties.length ? `
      <div class="space-y-3">
        <h4 class="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest">Involved Parties</h4>
        <div class="grid grid-cols-2 gap-3">
          ${parties.map(p => {
            const name    = typeof p === 'string' ? p : (p.name ?? p.legal_name ?? String(p));
            const role    = typeof p === 'object' ? (p.role ?? '') : '';
            const initial = (name[0] ?? '?').toUpperCase();
            return `
            <div class="flex items-center gap-3 p-3 bg-surface-container-lowest rounded-lg border border-outline-variant/10 shadow-sm">
              <div class="w-9 h-9 rounded-full bg-secondary-fixed flex items-center justify-center flex-shrink-0">
                <span class="text-on-secondary-fixed text-sm font-bold">${escHtml(initial)}</span>
              </div>
              <div class="min-w-0">
                <p class="text-sm font-bold text-primary truncate">${escHtml(name)}</p>
                ${role ? `<p class="text-[10px] font-semibold text-secondary uppercase tracking-wider truncate">${escHtml(role)}</p>` : ''}
              </div>
            </div>`;
          }).join('')}
        </div>
      </div>` : ''}
    </div>
    ${_metaStrip(ev)}
    ${_footer(_sourceLink(ev))}`;
}

function _renderParty(p) {
  const name    = p.legal_name ?? 'Unknown Party';
  const initial = (name[0] ?? '?').toUpperCase();
  const reps    = Array.isArray(p.project_party_reps) ? p.project_party_reps : [];

  return `
    <div class="px-8 py-6 border-b border-outline-variant/15 flex items-center justify-between flex-shrink-0">
      <div class="flex items-center gap-4">
        <div class="w-14 h-14 rounded-xl bg-primary-container flex items-center justify-center flex-shrink-0">
          <span class="text-on-primary text-xl font-black font-headline">${escHtml(initial)}</span>
        </div>
        <div>
          <h2 class="font-headline text-xl font-bold text-on-surface leading-tight">${escHtml(name)}</h2>
          <div class="flex items-center gap-2 mt-1 flex-wrap">
            ${p.entity_type ? `<span class="text-[10px] font-bold text-secondary uppercase tracking-widest">${escHtml(p.entity_type)}</span>` : ''}
            ${p.entity_type && p.role ? `<span class="text-on-surface-variant/30 text-xs">·</span>` : ''}
            ${p.role ? `<span class="text-xs font-medium text-on-surface-variant">${escHtml(p.role)}</span>` : ''}
            <span class="text-on-surface-variant/20 text-xs">·</span>
            <span class="text-[10px] text-on-surface-variant/40 font-mono">party_id: ${escHtml((p.party_id ?? ''))}</span>
          </div>
        </div>
      </div>
      ${_headerActions()}
    </div>
    <div class="flex-1 overflow-y-auto p-8 space-y-6 min-h-0">
      ${p.significance ? `<div>
        <label class="text-[10px] font-black uppercase tracking-widest text-on-surface-variant/60 mb-2 block">Significance</label>
        ${_sigBadge(p.significance)}
      </div>` : ''}
      ${p.role_description ? `<div>
        <label class="text-[10px] font-black uppercase tracking-widest text-on-surface-variant/60 mb-2 block">Role Description</label>
        <div class="bg-surface-container-low p-4 rounded-lg border border-outline-variant/10">
          <p class="text-sm text-on-surface leading-relaxed">${escHtml(p.role_description)}</p>
        </div>
      </div>` : ''}
      ${reps.length ? `<div>
        <label class="text-[10px] font-black uppercase tracking-widest text-on-surface-variant/60 mb-3 block">Representatives (${reps.length})</label>
        <div class="space-y-2">
          ${reps.map(r => {
            const repName = [r.first_name, r.last_name].filter(Boolean).join(' ') || 'Representative';
            const repInit = repName.split(' ').map(w => (w[0] ?? '')).join('').toUpperCase().slice(0, 2);
            const address = [r.address, r.postal_code, r.city].filter(Boolean).join(', ');
            return `
            <div class="flex items-start gap-3 p-4 bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10">
              <div class="w-9 h-9 rounded-full bg-secondary-container flex items-center justify-center flex-shrink-0">
                <span class="text-on-secondary-container text-xs font-bold">${escHtml(repInit)}</span>
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-sm font-bold text-on-surface">${escHtml(repName)}</p>
                ${r.rep_role ? `<p class="text-[10px] font-semibold text-secondary uppercase tracking-wide mt-0.5">${escHtml(r.rep_role)}</p>` : ''}
                <div class="flex flex-wrap gap-x-4 gap-y-0.5 mt-1.5">
                  ${r.email ? `<span class="text-[11px] text-on-surface-variant flex items-center gap-1"><span class="material-symbols-outlined text-[12px]">mail</span>${escHtml(r.email)}</span>` : ''}
                  ${r.phone ? `<span class="text-[11px] text-on-surface-variant flex items-center gap-1"><span class="material-symbols-outlined text-[12px]">phone</span>${escHtml(r.phone)}</span>` : ''}
                </div>
                ${address ? `<p class="text-[10px] text-on-surface-variant/50 mt-1">${escHtml(address)}</p>` : ''}
              </div>
            </div>`;
          }).join('')}
        </div>
      </div>` : ''}
    </div>
    ${_metaStrip(p)}
    ${_footer()}`;
}

function _renderDamage(d) {
  const title    = d.title ?? d.basis ?? d.category ?? 'Damage';
  const shortId  = (d.damage_id ?? '');
  const amount   = d.amount != null ? formatCurrency(d.amount, d.currency ?? 'NOK') : null;
  const evidence = Array.isArray(d.supporting_evidence)
    ? d.supporting_evidence
    : (d.supporting_evidence && typeof d.supporting_evidence === 'object'
        ? Object.values(d.supporting_evidence) : []);

  return `
    <div class="px-8 py-6 border-b border-outline-variant/15 flex items-center justify-between flex-shrink-0">
      <div class="flex items-center gap-4">
        <div class="w-12 h-12 bg-primary-container rounded-lg flex items-center justify-center flex-shrink-0">
          <span class="material-symbols-outlined text-2xl text-on-primary">payments</span>
        </div>
        <div>
          <h2 class="font-headline text-xl font-bold text-on-surface leading-tight">${escHtml(title)}</h2>
          <p class="text-[10px] text-on-surface-variant/50 font-mono mt-0.5">damage_id: ${escHtml(shortId)}</p>
        </div>
      </div>
      ${_headerActions()}
    </div>
    <div class="flex-1 overflow-y-auto p-8 space-y-6 min-h-0">
      ${amount ? `
      <div class="bg-surface-container-lowest p-6 rounded-xl border border-outline-variant/10 relative overflow-hidden">
        <div class="absolute top-0 right-0 p-4 opacity-[0.04]"><span class="material-symbols-outlined text-7xl">payments</span></div>
        <label class="text-[10px] font-black uppercase tracking-widest text-on-surface-variant/60 mb-1 block">Claimed Amount</label>
        <span class="text-3xl font-headline font-black text-primary">${escHtml(amount)}</span>
      </div>` : ''}
      <div class="flex flex-wrap gap-2">
        ${_sigBadge(d.significance)}
        ${d.category ? `<span class="inline-flex items-center px-3 py-1.5 rounded-full bg-surface-container text-on-surface-variant text-[10px] font-bold uppercase tracking-tight">${escHtml(d.category)}</span>` : ''}
        ${d.party_role ? `<span class="inline-flex items-center px-3 py-1.5 rounded-full bg-secondary-container/30 text-on-secondary-container text-[10px] font-bold uppercase tracking-tight">${escHtml(d.party_role)}</span>` : ''}
      </div>
      ${d.basis ? `<div>
        <label class="text-[10px] font-black uppercase tracking-widest text-on-surface-variant/60 mb-2 block">Basis</label>
        <div class="bg-surface-container-low p-4 rounded-lg border border-outline-variant/10">
          <p class="text-sm text-on-surface leading-relaxed">${escHtml(d.basis)}</p>
        </div>
      </div>` : ''}
      ${evidence.length ? `<div>
        <label class="text-[10px] font-black uppercase tracking-widest text-on-surface-variant/60 mb-2 block">Supporting Evidence</label>
        <ul class="space-y-2">
          ${evidence.map(ev => `
          <li class="flex gap-3 items-start p-3 bg-surface-container-lowest rounded-lg ring-1 ring-outline-variant/10">
            <span class="material-symbols-outlined text-[15px] text-secondary mt-0.5 flex-shrink-0">attach_file</span>
            <span class="text-sm text-on-surface">${escHtml(typeof ev === 'string' ? ev : JSON.stringify(ev))}</span>
          </li>`).join('')}
        </ul>
      </div>` : ''}
    </div>
    ${_metaStrip(d)}
    ${_footer(_sourceLink(d))}`;
}

// ────────────────────────────────────────────────────────────
// EDIT RENDERS
// ────────────────────────────────────────────────────────────

function _renderEditDeadline(d) {
  const shortId = (d.deadline_id ?? '');
  const iconHtml = `<div class="w-10 h-10 bg-primary-container rounded-lg flex items-center justify-center flex-shrink-0">
    <span class="material-symbols-outlined text-xl text-on-primary">alarm_on</span></div>`;

  return `
    ${_editHeader(iconHtml, d.title ?? d.description ?? 'Deadline', 'deadline_id', shortId)}
    <form id="entity-edit-form" class="flex flex-col md:flex-row flex-1 min-h-0">
      <div class="w-full md:w-[44%] p-8 space-y-5 border-b md:border-b-0 md:border-r border-outline-variant/10 overflow-y-auto"
           style="background:rgba(246,243,241,0.5);">
        ${_fg('Title', `<input type="text" name="title" value="${escHtml(d.title ?? '')}" class="${E.input}" placeholder="Deadline title">`)}
        ${_fg('Deadline Date', `<input type="date" name="deadline_date" value="${_isoToDate(d.deadline_date)}" class="${E.input}">`)}
        ${_fg('Responsible Party', `<input type="text" name="party_role" value="${escHtml(d.party_role ?? '')}" class="${E.input}" placeholder="Party role">`)}
      </div>
      <div class="w-full md:w-[56%] p-8 space-y-5 overflow-y-auto">
        ${_fg('Significance', _sigSelect(d.significance))}
        ${_fg('Description', `<textarea name="description" rows="6" class="${E.textarea}" placeholder="Describe this deadline…">${escHtml(d.description ?? '')}</textarea>`)}
      </div>
    </form>
    ${_metaStrip(d)}
    ${_editFooter()}`;
}

function _renderEditClaim(c) {
  const shortId  = (c.claim_id ?? '');
  const iconHtml = `<div class="w-10 h-10 bg-secondary/10 rounded-lg flex items-center justify-center flex-shrink-0">
    <span class="material-symbols-outlined text-xl text-secondary" style="font-variation-settings:'FILL' 1;">gavel</span></div>`;

  return `
    ${_editHeader(iconHtml, c.title ?? 'Claim', 'claim_id', shortId)}
    <form id="entity-edit-form" class="flex-1 overflow-y-auto p-8 space-y-5 min-h-0">
      ${_fg('Title', `<input type="text" name="title" value="${escHtml(c.title ?? '')}" class="${E.input}" placeholder="Claim title">`)}
      <div class="grid grid-cols-2 gap-4">
        ${_fg('Category', `<input type="text" name="category" value="${escHtml(c.category ?? '')}" class="${E.input}" placeholder="e.g. Intellectual Property">`)}
        ${_fg('Significance', _sigSelect(c.significance))}
      </div>
      <div class="grid grid-cols-2 gap-4">
        ${_fg('Party Role', `<input type="text" name="party_role" value="${escHtml(c.party_role ?? '')}" class="${E.input}" placeholder="e.g. Claimant">`)}
        ${_fg('Strength Assessment', _strengthSelect(c.strength_assessment))}
      </div>
      ${_fg('Factual Basis', `<textarea name="factual_basis" rows="4" class="${E.textarea}" placeholder="Key facts supporting this claim…">${escHtml(c.factual_basis ?? '')}</textarea>`)}
      ${_fg('Legal Basis', `<textarea name="legal_basis" rows="3" class="${E.textarea}" placeholder="Relevant statutes, case law…">${escHtml(c.legal_basis ?? '')}</textarea>`)}
      ${_fg('Defense / Counter-argument', `<textarea name="defense" rows="3" class="${E.textarea}" placeholder="Known defense arguments…">${escHtml(c.defense ?? '')}</textarea>`)}
      ${_fg('Relief Sought', `<textarea name="relief_sought" rows="3" class="${E.textarea}" placeholder="Remedies requested…">${escHtml(c.relief_sought ?? '')}</textarea>`)}
    </form>
    ${_metaStrip(c)}
    ${_editFooter()}`;
}

function _renderEditEvent(ev) {
  const shortId  = (ev.event_id ?? '');
  const iconHtml = `<div class="w-10 h-10 bg-primary-container rounded-lg flex items-center justify-center flex-shrink-0">
    <span class="material-symbols-outlined text-xl text-on-primary">event</span></div>`;

  return `
    ${_editHeader(iconHtml, ev.event_name ?? 'Event', 'event_id', shortId)}
    <form id="entity-edit-form" class="flex-1 overflow-y-auto p-8 space-y-5 min-h-0">
      ${_fg('Event Name', `<input type="text" name="event_name" value="${escHtml(ev.event_name ?? '')}" class="${E.input}" placeholder="Name of the event">`)}
      <div class="grid grid-cols-2 gap-4">
        ${_fg('Category', `<input type="text" name="category" value="${escHtml(ev.category ?? '')}" class="${E.input}" placeholder="e.g. Court Hearing">`)}
        ${_fg('Significance', _sigSelect(ev.significance))}
      </div>
      <div class="grid grid-cols-2 gap-4">
        ${_fg('Start Date', `<input type="date" name="event_start_date" value="${_isoToDate(ev.event_start_date)}" class="${E.input}">`)}
        ${_fg('End Date', `<input type="date" name="event_end_date" value="${_isoToDate(ev.event_end_date)}" class="${E.input}">`)}
      </div>
      <div class="flex items-center gap-3 py-1">
        <input type="checkbox" id="edit-disputed" value="true" ${ev.disputed ? 'checked' : ''}
               class="w-4 h-4 rounded border-outline-variant/30 text-secondary focus:ring-secondary/30 cursor-pointer">
        <label for="edit-disputed" class="text-sm font-medium text-on-surface cursor-pointer select-none">Mark as disputed</label>
      </div>
      ${_fg('Description', `<textarea name="description" rows="5" class="${E.textarea}" placeholder="What happened, context, significance…">${escHtml(ev.description ?? '')}</textarea>`)}
    </form>
    ${_metaStrip(ev)}
    ${_editFooter()}`;
}

function _renderEditParty(p) {
  const name     = p.legal_name ?? 'Unknown Party';
  const initial  = (name[0] ?? '?').toUpperCase();
  const shortId  = (p.party_id ?? '');
  const reps     = Array.isArray(p.project_party_reps) ? p.project_party_reps : [];
  const iconHtml = `
    <div class="w-12 h-12 rounded-xl bg-primary-container flex items-center justify-center flex-shrink-0">
      <span class="text-on-primary text-lg font-black font-headline">${escHtml(initial)}</span>
    </div>`;

  return `
    ${_editHeader(iconHtml, name, 'party_id', shortId)}
    <form id="entity-edit-form" class="flex-1 overflow-y-auto p-8 space-y-5 min-h-0">
      ${_fg('Legal Name', `<input type="text" name="legal_name" value="${escHtml(p.legal_name ?? '')}" class="${E.input}" placeholder="Full legal name">`)}
      <div class="grid grid-cols-2 gap-4">
        ${_fg('Entity Type', `<input type="text" name="entity_type" value="${escHtml(p.entity_type ?? '')}" class="${E.input}" placeholder="e.g. Corporation, Individual">`)}
        ${_fg('Role in Matter', `<input type="text" name="role" value="${escHtml(p.role ?? '')}" class="${E.input}" placeholder="e.g. Claimant, Defendant">`)}
      </div>
      ${_fg('Significance', _sigSelect(p.significance))}
      ${_fg('Role Description', `<textarea name="role_description" rows="4" class="${E.textarea}" placeholder="Describe this party's involvement…">${escHtml(p.role_description ?? '')}</textarea>`)}
      ${reps.length ? `
      <div>
        <label class="${E.label}">Representatives (${reps.length}) — read-only, managed by agent</label>
        <div class="space-y-1.5">
          ${reps.map(r => {
            const repName = [r.first_name, r.last_name].filter(Boolean).join(' ') || 'Representative';
            return `<div class="flex items-center gap-2 px-3 py-2 bg-surface-container rounded-lg text-xs text-on-surface-variant">
              <span class="material-symbols-outlined text-[14px]">person</span>
              <span class="font-semibold">${escHtml(repName)}</span>
              ${r.rep_role ? `<span class="text-outline">·</span><span>${escHtml(r.rep_role)}</span>` : ''}
            </div>`;
          }).join('')}
        </div>
      </div>` : ''}
    </form>
    ${_metaStrip(p)}
    ${_editFooter()}`;
}

function _renderEditDamage(d) {
  const shortId  = (d.damage_id ?? '');
  const iconHtml = `<div class="w-10 h-10 bg-primary-container rounded-lg flex items-center justify-center flex-shrink-0">
    <span class="material-symbols-outlined text-xl text-on-primary">payments</span></div>`;

  return `
    ${_editHeader(iconHtml, d.title ?? d.basis ?? 'Damage', 'damage_id', shortId)}
    <form id="entity-edit-form" class="flex-1 overflow-y-auto p-8 space-y-5 min-h-0">
      ${_fg('Title', `<input type="text" name="title" value="${escHtml(d.title ?? '')}" class="${E.input}" placeholder="Damage title">`)}
      <div class="grid grid-cols-3 gap-4">
        ${_fg('Amount', `<input type="number" name="amount" value="${escHtml(d.amount != null ? String(d.amount) : '')}" class="${E.input}" placeholder="0" step="any" min="0">`)}
        ${_fg('Currency', `<input type="text" name="currency" value="${escHtml(d.currency ?? 'NOK')}" class="${E.input}" placeholder="NOK">`)}
        ${_fg('Category', `<input type="text" name="category" value="${escHtml(d.category ?? '')}" class="${E.input}" placeholder="e.g. Lost Revenue">`)}
      </div>
      <div class="grid grid-cols-2 gap-4">
        ${_fg('Party Role', `<input type="text" name="party_role" value="${escHtml(d.party_role ?? '')}" class="${E.input}" placeholder="e.g. Claimant">`)}
        ${_fg('Significance', _sigSelect(d.significance))}
      </div>
      ${_fg('Basis', `<textarea name="basis" rows="3" class="${E.textarea}" placeholder="Legal or factual basis for this damage claim…">${escHtml(d.basis ?? '')}</textarea>`)}
      ${_fg('Supporting Evidence', `<textarea name="supporting_evidence" rows="4" class="${E.textarea}"
             placeholder="One item per line…">${escHtml(_evidenceToText(d.supporting_evidence))}</textarea>
             <p class="text-[10px] text-on-surface-variant/40 mt-1">One entry per line — stored as a list</p>`)}
    </form>
    ${_metaStrip(d)}
    ${_editFooter()}`;
}

