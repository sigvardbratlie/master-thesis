// ============================================================
// PROJECT DASHBOARD — single project view
// Layout ref:  new-ui/project_dashboard.html
// Logic ref:   ui/src/ui/ui_components/chat_component.py
//              ui/src/ui/ui_components/project_component.py
//              ui/src/ui/services/streaming_service.py
// ============================================================

import {
  loadProjectMeta,
  loadProjectEvents,
  loadProjectParties,
  loadProjectClaims,
  loadProjectDeadlines,
  loadProjectDamages,
  loadProjectAttachments,
  loadProjectEmails,
  loadEmailBody,
} from '../api.js';
import { fetchFileAsObjectUrl, fetchTextFile } from '../storage.js';
import { renderSidebar, bindSidebarEvents } from '../components/sidebar.js';
import { renderTopbar }                     from '../components/topbar.js';
import { formatDate, skeleton, escHtml }    from '../utils.js';
import { initPopovers, registerItems }      from '../components/popovers.js';
import { marked }                           from 'marked';
import { chatLog }                          from '../logger.js';

// Configure marked: safe, breaks on newline
marked.setOptions({ breaks: true, gfm: true });
const md = (text) => marked.parse(text ?? '');

// ── Email store — avoids data-attribute encoding issues ───────
const _emailStore  = new Map(); // key: email_id → email object
const _attachStore = new Map(); // key: file_id  → attachment object
let   _viewerBound = false;     // prevents duplicate document listeners across navigations

export async function renderProject(params) {
  const projectId = params.id;

  document.getElementById('app').innerHTML = `
    ${renderSidebar()}
    <div class="ml-64 min-h-screen bg-surface flex flex-col">
      ${renderTopbar({
        title: 'Loading...',
        breadcrumb: { label: 'Projects', href: '#/' },
        actions: `
          <a href="#/chat/${projectId}"
             class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-container text-on-surface-variant text-xs font-headline font-semibold hover:bg-primary hover:text-on-primary transition-all">
            <span class="material-symbols-outlined text-[16px]" style="font-variation-settings:'FILL' 1">chat</span>
            Open Chat
          </a>`,
      })}
      <div id="project-body" class="flex-1 flex">
        <div class="flex-1 p-10 space-y-4">${skeleton(5)}</div>
      </div>
    </div>`;

  bindSidebarEvents();

  // Load meta first — needed for title + shell structure
  let meta;
  try {
    meta = await loadProjectMeta(projectId);
  } catch (err) {
    document.getElementById('project-body').innerHTML =
      `<div class="p-10 text-error text-sm">${err.message}</div>`;
    return;
  }

  buildProjectShell(projectId, meta);

  // Helper: fetch → render a section, fail gracefully per section
  function loadSection(secId, fetchFn, renderFn) {
    fetchFn().then(data => {
      const el = document.getElementById(`sec-${secId}`);
      if (el) el.innerHTML = renderFn(data);
    }).catch(err => {
      const el = document.getElementById(`sec-${secId}`);
      if (el) el.innerHTML = `<p class="text-error text-xs py-2">${err.message}</p>`;
    });
  }

  // Fire all sections in parallel
  loadSection('timeline',  () => loadProjectEvents(projectId),      buildTimelineInner);
  loadSection('parties',   () => loadProjectParties(projectId),     buildPartiesInner);
  loadSection('claims',    () => loadProjectClaims(projectId),      buildClaimsSection);
  loadSection('deadlines', () => loadProjectDeadlines(projectId),   buildDeadlinesInner);
  loadSection('damages',   () => loadProjectDamages(projectId),     buildDamagesInner);

  // Documents section needs both attachments + emails
  Promise.all([loadProjectAttachments(projectId), loadProjectEmails(projectId)])
    .then(([attachments, emails]) => {
      // Update subtitle with counts
      const btn = document.querySelector('[data-sec="documents"]');
      if (btn) {
        const sub = btn.querySelector('p');
        if (sub) sub.textContent = `${attachments.length} files · ${emails.length} emails`;
      }
      const el = document.getElementById('sec-documents');
      if (el) el.innerHTML = buildAttachmentsList(attachments, emails);
    })
    .catch(err => {
      const el = document.getElementById('sec-documents');
      if (el) el.innerHTML = `<p class="text-error text-xs py-2">${err.message}</p>`;
    });
}

// ── Section helper (collapsible) ─────────────────────────────

function sec(id, title, subtitle, content) {
  return `
    <div class="border border-outline-variant/10 rounded-2xl overflow-hidden bg-surface-container-lowest">
      <button class="sec-toggle w-full flex items-center justify-between px-6 py-4 hover:bg-surface-container transition-colors group"
              data-sec="${id}">
        <div class="text-left">
          <h3 class="font-headline font-bold text-base text-primary">${title}</h3>
          ${subtitle ? `<p class="text-on-surface-variant text-xs mt-0.5">${subtitle}</p>` : ''}
        </div>
        <span class="material-symbols-outlined text-[20px] text-on-surface-variant/40 group-hover:text-secondary transition-all sec-icon">
          expand_less
        </span>
      </button>
      <div id="sec-${id}" class="px-6 pb-6 pt-1">${content}</div>
    </div>`;
}

// ── Shell layout ─────────────────────────────────────────────

function buildProjectShell(projectId, meta) {
  const title = meta.title ?? 'Untitled Project';

  // Update topbar title
  document.querySelector('#app header h2').textContent = title;

  const sectionSkeleton = `<div class="space-y-2 py-2">${skeleton(2)}</div>`;

  document.getElementById('project-body').innerHTML = `
    <div class="flex-1 overflow-y-auto min-w-0" id="factsheet-panel">
      <div class="max-w-4xl mx-auto px-10 py-10">

        <!-- Case title -->
        <div class="mb-8">
          <h1 class="font-headline font-black text-3xl text-primary tracking-tight leading-tight">${escHtml(title)}</h1>
          <p class="text-xs text-on-surface-variant/50 font-mono mt-2">${projectId}</p>
        </div>

        <div class="space-y-4">
          ${sec('background', 'Background', null,
            meta.background
              ? `<p class="text-sm text-on-surface font-body leading-relaxed whitespace-pre-line">${escHtml(meta.background)}</p>`
              : `<p class="text-sm text-on-surface-variant font-body italic">No background recorded.</p>`
          )}

          ${sec('timeline',  'Case Chronology', 'Key events · high-significance shown in full', sectionSkeleton)}
          ${sec('parties',   'Active Parties',  null, sectionSkeleton)}
          ${sec('claims',    'Claims',          null, sectionSkeleton)}
          ${sec('deadlines', 'Deadlines',       null, sectionSkeleton)}
          ${sec('damages',   'Damages',         null, sectionSkeleton)}
          ${sec('documents', 'Documents',       'Loading…', sectionSkeleton)}
        </div>

        <div class="mt-8 pt-4 border-t border-outline-variant/10 flex items-center justify-between text-[10px] text-on-surface-variant/30 font-body">
          <span>Created ${formatDate(meta.created_at)}</span>
        </div>
      </div>
    </div>`;

  // Append viewer modal only
  const modal = document.createElement('div');
  modal.innerHTML = buildViewerModal();
  document.getElementById('app').appendChild(modal.firstElementChild);

  // Init entity popovers (idempotent)
  initPopovers();

  bindProjectEvents(projectId);
  bindViewerEvents();
}

// ── Timeline ─────────────────────────────────────────────────

function buildTimelineInner(events) {
  if (!events.length) {
    return `<p class="text-on-surface-variant text-sm font-body py-4">No events recorded yet.</p>`;
  }

  registerItems('event', events, 'event_id');

  const sorted = [...events].sort((a, b) =>
    new Date(a.event_start_date ?? 0) - new Date(b.event_start_date ?? 0)
  );

  const isHigh = e => (e.significance ?? '').toLowerCase() === 'high';

  // Group non-high events by year-month
  const monthMap = new Map();
  sorted.filter(e => !isHigh(e)).forEach(ev => {
    const d   = ev.event_start_date ? new Date(ev.event_start_date) : null;
    const key = d ? `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}` : 'z-unknown';
    if (!monthMap.has(key)) monthMap.set(key, []);
    monthMap.get(key).push(ev);
  });

  const items = [
    ...sorted.filter(isHigh).map(ev => ({ type: 'event', ev, sort: +new Date(ev.event_start_date ?? 0) })),
    ...[...monthMap.entries()].map(([key, evs]) => ({
      type: 'group', evs, key,
      sort: key === 'z-unknown' ? 0 : +new Date(key + '-01'),
    })),
  ].sort((a, b) => a.sort - b.sort);

  return `<div class="space-y-0">${items.map((item, i) => {
    const isLast = i === items.length - 1;
    const line   = isLast ? '' : `<div class="w-px flex-1 bg-outline-variant/20 my-1 ml-px"></div>`;

    if (item.type === 'event') {
      const ev      = item.ev;
      const date    = ev.event_start_date ? formatDate(ev.event_start_date, { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
      const endDate = ev.event_end_date   ? ` – ${formatDate(ev.event_end_date, { day: 'numeric', month: 'short', year: 'numeric' })}` : '';
      return `
        <div class="flex gap-5 pb-6">
          <div class="flex flex-col items-center flex-shrink-0 w-3">
            <div class="w-3 h-3 rounded-full bg-primary ring-4 ring-primary/15 flex-shrink-0 mt-1"></div>
            ${line}
          </div>
          <div class="flex-1 min-w-0 pb-1 cursor-pointer popover-item group"
               data-popover-type="event" data-popover-id="${escHtml(ev.event_id)}">
            <p class="text-[10px] font-bold text-secondary uppercase tracking-wider">${date}${endDate}</p>
            <h4 class="text-sm font-bold text-on-surface mt-0.5 leading-snug group-hover:text-secondary transition-colors">${escHtml(ev.event_name ?? ev.description ?? '')}</h4>
            ${ev.event_name && ev.description ? `<p class="text-xs text-on-surface-variant mt-1 leading-relaxed">${escHtml(ev.description)}</p>` : ''}
            <div class="flex flex-wrap gap-1 mt-1.5">
              ${ev.disputed ? `<span class="px-1.5 py-0.5 rounded bg-error-container/40 text-error text-[9px] font-bold uppercase">Disputed</span>` : ''}
              ${ev.category ? `<span class="px-1.5 py-0.5 rounded bg-surface-container text-on-surface-variant text-[9px] font-bold uppercase">${escHtml(ev.category)}</span>` : ''}
            </div>
          </div>
        </div>`;
    } else {
      const label = item.key !== 'z-unknown'
        ? new Date(item.key + '-01').toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
        : 'Undated';
      return `
        <div class="flex gap-5 pb-4">
          <div class="flex flex-col items-center flex-shrink-0 w-3">
            <div class="w-2 h-2 rounded-full bg-secondary/30 ring-2 ring-secondary/15 flex-shrink-0 mt-1.5"></div>
            ${line}
          </div>
          <div class="flex items-center gap-2 pb-1">
            <span class="text-[10px] text-on-surface-variant">${label}</span>
            <span class="px-2 py-0.5 rounded-full bg-surface-container text-on-surface-variant text-[10px] font-semibold">
              ${item.evs.length} event${item.evs.length > 1 ? 's' : ''}
            </span>
          </div>
        </div>`;
    }
  }).join('')}</div>`;
}

// ── Parties ───────────────────────────────────────────────────

function buildPartiesInner(parties) {
  if (!parties.length) return `<p class="text-on-surface-variant text-sm italic py-2">No parties recorded.</p>`;
  registerItems('party', parties, 'party_id');
  return `<div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
    ${parties.map(p => {
      const name    = p.legal_name ?? p.party_name ?? p.name ?? 'Unknown';
      const initial = name[0].toUpperCase();
      const role    = p.role ?? p.party_role ?? '';
      const type    = p.entity_type ? ` · ${p.entity_type}` : '';
      return `
        <div class="flex items-center gap-3 p-3 bg-surface-container rounded-xl ring-1 ring-transparent
                    hover:ring-secondary/20 transition-all cursor-pointer popover-item"
             data-popover-type="party" data-popover-id="${escHtml(p.party_id)}">
          <div class="w-9 h-9 rounded-lg bg-primary-container flex items-center justify-center flex-shrink-0">
            <span class="text-on-primary text-sm font-bold">${escHtml(initial)}</span>
          </div>
          <div class="min-w-0">
            <p class="text-sm font-bold text-on-surface truncate">${escHtml(name)}</p>
            <p class="text-[10px] font-bold text-secondary uppercase tracking-tight">${escHtml(role + type)}</p>
          </div>
        </div>`;
    }).join('')}
  </div>`;
}

function buildClaimsSection(claims) {
  if (claims.length) registerItems('claim', claims, 'claim_id');
  const items = claims.length
    ? claims.map(c => {
        const relief  = c.relief_sought    ? `<p class="text-[10px] text-secondary font-bold mt-1 uppercase tracking-wide">Relief: ${escHtml(c.relief_sought)}</p>` : '';
        const basis   = c.legal_basis      ? `<p class="text-[10px] text-on-surface-variant mt-0.5">${escHtml(c.legal_basis)}</p>` : '';
        const role    = c.party_role       ? `<span class="px-1.5 py-0.5 rounded bg-secondary-container/30 text-on-secondary-container text-[9px] font-bold uppercase">${escHtml(c.party_role)}</span>` : '';
        const cat     = c.category         ? `<span class="px-1.5 py-0.5 rounded bg-surface-container text-on-surface-variant text-[9px] font-bold uppercase">${escHtml(c.category)}</span>` : '';
        const title   = c.title ?? '';
        const desc    = c.factual_basis ?? c.defense ?? '';
        return `
          <div class="p-4 bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10
                      hover:ring-secondary/20 transition-all cursor-pointer popover-item"
               data-popover-type="claim" data-popover-id="${escHtml(c.claim_id)}">
            <div class="flex items-start justify-between gap-2 mb-1">
              <div class="min-w-0">
                ${title ? `<p class="text-xs font-bold text-secondary uppercase tracking-tight mb-0.5">${escHtml(title)}</p>` : ''}
                <p class="text-sm font-semibold text-on-surface leading-snug">${escHtml(desc)}</p>
              </div>
              <div class="flex gap-1 flex-shrink-0">${role}${cat}</div>
            </div>
            ${basis}${relief}
          </div>`;
      }).join('')
    : `<p class="text-on-surface-variant text-sm font-body py-4">No claims recorded. Ask the agent to identify claims.</p>`;

  return `
    <h3 class="font-headline font-bold text-lg text-primary mb-1">Claims</h3>
    <p class="text-on-surface-variant text-xs mb-5">Legal claims and requested relief</p>
    <div class="space-y-3">${items}</div>`;
}

// ── Deadlines / Damages (individual sections) ─────────────────

function buildDeadlinesInner(deadlines) {
  if (!deadlines.length) return `<p class="text-on-surface-variant text-sm italic py-2">No deadlines recorded.</p>`;
  registerItems('deadline', deadlines, 'deadline_id');
  return `<div class="space-y-2">
    ${deadlines.map(d => `
      <div class="flex items-center justify-between p-3 bg-surface-container rounded-xl ring-1 ring-outline-variant/10
                  hover:ring-secondary/20 transition-all cursor-pointer popover-item"
           data-popover-type="deadline" data-popover-id="${escHtml(d.deadline_id)}">
        <div class="min-w-0">
          ${d.title ? `<p class="text-[10px] font-bold text-secondary uppercase tracking-tight mb-0.5">${escHtml(d.title)}</p>` : ''}
          <p class="text-sm font-semibold text-on-surface truncate">${escHtml(d.description ?? '')}</p>
          <p class="text-[10px] text-secondary font-bold mt-0.5">${formatDate(d.deadline_date ?? d.date)}</p>
        </div>
        <span class="material-symbols-outlined text-[18px] text-tertiary-fixed-dim flex-shrink-0 ml-3">event</span>
      </div>`).join('')}
  </div>`;
}

function buildDamagesInner(damages) {
  if (!damages.length) return `<p class="text-on-surface-variant text-sm italic py-2">No damages recorded.</p>`;
  registerItems('damage', damages, 'damage_id');
  return `<div class="space-y-2">
    ${damages.map(d => {
      const desc   = d.basis ?? d.category ?? '';
      const amount = d.amount != null ? `${d.currency ? escHtml(d.currency) + ' ' : ''}${escHtml(String(d.amount))}` : '';
      return `
        <div class="flex items-center justify-between p-3 bg-surface-container rounded-xl ring-1 ring-outline-variant/10
                    hover:ring-secondary/20 transition-all cursor-pointer popover-item"
             data-popover-type="damage" data-popover-id="${escHtml(d.damage_id)}">
          <div class="min-w-0">
            ${d.title ? `<p class="text-[10px] font-bold text-secondary uppercase tracking-tight mb-0.5">${escHtml(d.title)}</p>` : ''}
            <p class="text-sm font-semibold text-on-surface">${escHtml(desc)}</p>
            ${d.party_role ? `<p class="text-[10px] text-secondary font-bold uppercase mt-0.5">${escHtml(d.party_role)}</p>` : ''}
          </div>
          ${amount ? `<span class="text-sm font-bold text-secondary flex-shrink-0 ml-4 whitespace-nowrap">${amount}</span>` : ''}
        </div>`;
    }).join('')}
  </div>`;
}

const TEXT_MIME_TYPES = new Set(['text/plain', 'text/markdown', 'text/csv', 'text/x-markdown']);
const TEXT_EXTENSIONS = new Set(['.txt', '.md', '.markdown', '.csv']);

function fileViewType(filename, mimeType) {
  const ext = filename ? filename.slice(filename.lastIndexOf('.')).toLowerCase() : '';
  if (mimeType === 'application/pdf') return 'pdf';
  if (TEXT_MIME_TYPES.has(mimeType) || TEXT_EXTENSIONS.has(ext)) return 'text';
  return null; // unsupported
}

function buildAttachmentsList(attachments, emails) {
  _attachStore.clear();
  attachments.forEach(a => { if (a.file_id) _attachStore.set(a.file_id, a); });

  const attItems = attachments.map(a => {
    const vtype = fileViewType(a.filename ?? '', a.file_type ?? '');
    const isPdf = vtype === 'pdf';
    const isText = vtype === 'text';
    const canOpen = isPdf || isText;
    const icon = isPdf ? 'picture_as_pdf' : isText ? 'article' : 'description';
    const ext = (a.filename ?? '').slice((a.filename ?? '').lastIndexOf('.')).toLowerCase();
    const isMarkdown = ext === '.md' || ext === '.markdown';
    return `
    <div class="flex items-center gap-3 p-3 bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10
                hover:ring-secondary/20 transition-all group ${canOpen ? 'cursor-pointer att-item' : 'opacity-60'}"
         data-type="${vtype ?? 'pdf'}" data-path="${escHtml(a.path ?? '')}" data-name="${escHtml(a.filename ?? '')}" data-file-type="${escHtml(a.file_type ?? 'application/pdf')}" data-is-markdown="${isMarkdown}">
      <span class="material-symbols-outlined text-[20px] text-secondary">${icon}</span>
      <div class="flex-1 min-w-0">
        <p class="text-xs font-semibold text-on-surface truncate">${escHtml(a.filename ?? '')}</p>
        <p class="text-[10px] text-on-surface-variant">${formatDate(a.file_date ?? a.created_at)}</p>
      </div>
      ${canOpen ? `<span class="material-symbols-outlined text-[16px] text-on-surface-variant/30 group-hover:text-secondary transition-colors">open_in_new</span>` : ''}
    </div>`;
  });

  _emailStore.clear();
  const emailItems = emails.map(e => {
    const id = e.email_id ?? e.message_id ?? String(Math.random());
    _emailStore.set(id, e);
    return `
    <div class="flex items-center gap-3 p-3 bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10
                hover:ring-secondary/20 transition-all group cursor-pointer att-item"
         data-type="email" data-email-id="${escHtml(id)}">
      <span class="material-symbols-outlined text-[20px] text-secondary">mail</span>
      <div class="flex-1 min-w-0">
        <p class="text-xs font-semibold text-on-surface truncate">${escHtml(e.subject ?? 'No subject')}</p>
        <p class="text-[10px] text-on-surface-variant">${escHtml(e.from_addr ?? '')} · ${formatDate(e.date)}</p>
      </div>
      <span class="material-symbols-outlined text-[16px] text-on-surface-variant/30 group-hover:text-secondary transition-colors">open_in_new</span>
    </div>`;
  });

  if (!attItems.length && !emailItems.length) {
    return `<p class="text-on-surface-variant text-sm font-body py-2">No documents attached.</p>`;
  }

  return `<div class="grid grid-cols-2 gap-2">${[...attItems, ...emailItems].join('')}</div>`;
}

// ── Viewer modal ──────────────────────────────────────────────

function buildViewerModal() {
  return `
    <div id="viewer-modal" class="hidden fixed inset-0 z-[200] flex flex-col">
      <!-- Backdrop -->
      <div id="viewer-backdrop" class="absolute inset-0 bg-black/40 backdrop-blur-sm"></div>

      <!-- Panel -->
      <div class="relative m-6 flex-1 flex flex-col bg-surface-container-lowest rounded-2xl shadow-[0_32px_80px_-16px_rgba(0,0,0,0.3)] overflow-hidden ring-1 ring-outline-variant/10">

        <!-- Header -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-outline-variant/10 flex-shrink-0">
          <div class="flex items-center gap-3 min-w-0">
            <span id="viewer-icon" class="material-symbols-outlined text-[20px] text-secondary">description</span>
            <div class="min-w-0">
              <p id="viewer-title" class="font-headline font-bold text-primary truncate text-sm"></p>
              <p id="viewer-meta"  class="text-[10px] text-on-surface-variant mt-0.5"></p>
            </div>
          </div>
          <button id="viewer-close"
            class="p-2 rounded-lg hover:bg-surface-container transition-colors text-on-surface-variant hover:text-primary">
            <span class="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        <!-- Content -->
        <div id="viewer-body" class="flex-1 overflow-hidden relative">
          <!-- Loading state -->
          <div id="viewer-loading" class="absolute inset-0 flex items-center justify-center">
            <div class="flex flex-col items-center gap-3">
              <div class="flex gap-1">
                <span class="w-2 h-2 bg-secondary rounded-full animate-bounce" style="animation-delay:0ms"></span>
                <span class="w-2 h-2 bg-secondary rounded-full animate-bounce" style="animation-delay:150ms"></span>
                <span class="w-2 h-2 bg-secondary rounded-full animate-bounce" style="animation-delay:300ms"></span>
              </div>
              <p class="text-sm text-on-surface-variant">Loading document...</p>
            </div>
          </div>

          <!-- PDF iframe -->
          <iframe id="viewer-iframe"
            class="hidden w-full h-full border-0"
            title="Document viewer">
          </iframe>

          <!-- Email body — Outlook-style -->
          <div id="viewer-email" class="hidden h-full overflow-y-auto flex flex-col">
            <div id="viewer-email-headers" class="flex-shrink-0 bg-surface-container-low"></div>
            <div id="viewer-email-body" class="flex-1 px-8 py-6 overflow-y-auto"></div>
          </div>

          <!-- Text / Markdown viewer -->
          <div id="viewer-text" class="hidden h-full overflow-y-auto px-10 py-8">
            <div id="viewer-text-body"
              class="prose prose-sm max-w-3xl mx-auto text-on-surface font-body leading-relaxed
                     prose-headings:font-headline prose-headings:text-primary
                     prose-code:bg-surface-container prose-code:px-1 prose-code:rounded prose-code:text-xs
                     prose-pre:bg-surface-container prose-pre:rounded-xl prose-pre:text-xs">
            </div>
          </div>

          <!-- Error state -->
          <div id="viewer-error" class="hidden absolute inset-0 flex items-center justify-center">
            <div class="text-center">
              <span class="material-symbols-outlined text-4xl text-error/40 mb-3 block">error</span>
              <p id="viewer-error-msg" class="text-sm text-error"></p>
            </div>
          </div>
        </div>
      </div>
    </div>`;
}

function bindViewerEvents() {
  // Close on backdrop or button — scoped to modal elements, safe to re-add
  document.getElementById('viewer-close')?.addEventListener('click', closeViewer);
  document.getElementById('viewer-backdrop')?.addEventListener('click', closeViewer);

  // Keydown + att-item click: use { once: false } but guard with a module-level flag
  // so we don't stack listeners across navigations
  if (!_viewerBound) {
    _viewerBound = true;
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeViewer(); });
    document.addEventListener('click', async (e) => {
      const item = e.target.closest('.att-item');
      if (!item) return;
      const type = item.dataset.type;
      if (type === 'pdf')   await openPdfViewer(item);
      if (type === 'text')  await openTextViewer(item);
      if (type === 'email') await openEmailViewer(item.dataset.emailId);
    });
    document.addEventListener('open-source', async (e) => {
      const { type, id } = e.detail ?? {};
      if (!type || !id) return;
      if (type === 'email') {
        await openEmailViewer(id);
      } else {
        const a = _attachStore.get(id);
        if (!a) return;
        const vtype = fileViewType(a.filename ?? '', a.file_type ?? '');
        const ext   = (a.filename ?? '').slice((a.filename ?? '').lastIndexOf('.')).toLowerCase();
        const fakeItem = {
          dataset: {
            type: vtype,
            path: a.path ?? '',
            name: a.filename ?? '',
            fileType: a.file_type ?? 'application/pdf',
            isMarkdown: String(ext === '.md' || ext === '.markdown'),
          },
        };
        if (vtype === 'pdf')  await openPdfViewer(fakeItem);
        if (vtype === 'text') await openTextViewer(fakeItem);
      }
    });
  }
}

function openViewer(title, meta, icon = 'description') {
  document.getElementById('viewer-title').textContent = title;
  document.getElementById('viewer-meta').textContent  = meta;
  document.getElementById('viewer-icon').textContent  = icon;
  document.getElementById('viewer-loading').classList.remove('hidden');
  document.getElementById('viewer-iframe').classList.add('hidden');
  document.getElementById('viewer-email').classList.add('hidden');
  document.getElementById('viewer-text').classList.add('hidden');
  document.getElementById('viewer-error').classList.add('hidden');
  document.getElementById('viewer-modal').classList.remove('hidden');
}

function closeViewer() {
  const modal   = document.getElementById('viewer-modal');
  const iframe  = document.getElementById('viewer-iframe');
  if (iframe) iframe.src = '';   // stop loading / free memory
  modal?.classList.add('hidden');
}

async function openPdfViewer(item) {
  const path        = item.dataset.path;
  const name        = item.dataset.name;
  const contentType = item.dataset.fileType || 'application/pdf';
  openViewer(name, 'PDF Document', 'picture_as_pdf');

  try {
    chatLog.info({ path }, 'Fetching PDF via backend proxy');
    const url    = await fetchFileAsObjectUrl(path, contentType);
    const iframe = document.getElementById('viewer-iframe');
    iframe.onload = () => {
      document.getElementById('viewer-loading').classList.add('hidden');
      iframe.classList.remove('hidden');
    };
    iframe.src = url;
  } catch (err) {
    chatLog.error({ err: err.message }, 'PDF viewer error');
    document.getElementById('viewer-loading').classList.add('hidden');
    document.getElementById('viewer-error-msg').textContent = err.message;
    document.getElementById('viewer-error').classList.remove('hidden');
  }
}

async function openTextViewer(item) {
  const path       = item.dataset.path;
  const name       = item.dataset.name;
  const isMarkdown = item.dataset.isMarkdown === 'true';
  openViewer(name, isMarkdown ? 'Markdown Document' : 'Text Document', 'article');

  try {
    chatLog.info({ path, isMarkdown }, 'Fetching text file via backend proxy');
    const text   = await fetchTextFile(path);
    const bodyEl = document.getElementById('viewer-text-body');
    bodyEl.innerHTML = isMarkdown ? md(text) : `<pre class="whitespace-pre-wrap">${escHtml(text)}</pre>`;
    document.getElementById('viewer-loading').classList.add('hidden');
    document.getElementById('viewer-text').classList.remove('hidden');
  } catch (err) {
    chatLog.error({ err: err.message }, 'Text viewer error');
    document.getElementById('viewer-loading').classList.add('hidden');
    document.getElementById('viewer-error-msg').textContent = err.message;
    document.getElementById('viewer-error').classList.remove('hidden');
  }
}

// Parse "Display Name <email@domain>" or plain "email@domain"
function parseEmailAddr(raw) {
  const m = (raw ?? '').match(/^(.*?)\s*<(.+?)>$/);
  if (m) return { name: m[1].trim(), email: m[2].trim() };
  return { name: '', email: (raw ?? '').trim() };
}

async function openEmailViewer(emailId) {
  const e = _emailStore.get(emailId);
  if (!e) {
    chatLog.warn({ emailId }, 'openEmailViewer — email not found in store');
    return;
  }

  const subject = e.subject   ?? '(no subject)';
  const from    = parseEmailAddr(e.from_addr ?? '');
  const to      = Array.isArray(e.to) ? e.to.join(', ') : (e.to ?? '');
  const cc      = Array.isArray(e.cc) ? e.cc.join(', ') : (e.cc ?? '');
  const date    = e.date ?? '';

  openViewer(subject, from.email || from.name, 'mail');

  try {
    chatLog.info({ emailId }, 'Fetching email body on-demand');
    const body = await loadEmailBody(emailId);

    // Initials avatar from sender name or email
    const displayName = from.name || from.email;
    const initials    = displayName.split(/[\s@<>]+/).filter(Boolean).map(p => p[0]).join('').toUpperCase().slice(0, 2) || '?';
    const dateStr     = date ? new Date(date).toLocaleString('no-NO', { dateStyle: 'long', timeStyle: 'short' }) : '';

    // "To: A, B · Cc: C" compact recipient line
    const recipientLine = [
      to ? `Til: ${escHtml(to)}` : '',
      cc ? `Cc: ${escHtml(cc)}`  : '',
    ].filter(Boolean).join(' &nbsp;·&nbsp; ');

    document.getElementById('viewer-email-headers').innerHTML = `
      <!-- Subject -->
      <h2 class="font-headline font-bold text-xl text-on-surface mb-4 px-8 pt-6">${escHtml(subject)}</h2>

      <!-- Sender row — Outlook style -->
      <div class="flex items-start gap-4 px-8 pb-5 border-b border-outline-variant/10">
        <div class="w-10 h-10 rounded-full bg-primary-container flex items-center justify-center flex-shrink-0 mt-0.5">
          <span class="text-on-primary text-sm font-bold">${escHtml(initials)}</span>
        </div>
        <div class="flex-1 min-w-0">
          <div class="flex items-start justify-between gap-6">
            <div class="min-w-0">
              <p class="text-sm font-semibold text-on-surface leading-snug">
                ${escHtml(from.name || from.email)}
                ${from.name ? `<span class="font-normal text-on-surface-variant text-xs">&lt;${escHtml(from.email)}&gt;</span>` : ''}
              </p>
              ${recipientLine ? `<p class="text-xs text-on-surface-variant mt-0.5">${recipientLine}</p>` : ''}
            </div>
            <p class="text-[11px] text-on-surface-variant flex-shrink-0 mt-0.5">${escHtml(dateStr)}</p>
          </div>
        </div>
      </div>`;

    const bodyEl = document.getElementById('viewer-email-body');
    bodyEl.style.whiteSpace = 'pre-wrap';
    bodyEl.style.fontSize   = '0.875rem';
    bodyEl.style.lineHeight = '1.6';
    bodyEl.textContent = body || '(no body)';

    document.getElementById('viewer-loading').classList.add('hidden');
    document.getElementById('viewer-email').classList.remove('hidden');
  } catch (err) {
    chatLog.error({ err: err.message, emailId }, 'Email body fetch failed');
    document.getElementById('viewer-loading').classList.add('hidden');
    document.getElementById('viewer-error-msg').textContent = err.message;
    document.getElementById('viewer-error').classList.remove('hidden');
  }
}


// ── Project events (collapsible sections only) ────────────────

function bindProjectEvents(_projectId) {
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.sec-toggle');
    if (!btn) return;
    const id   = btn.dataset.sec;
    const body = document.getElementById(`sec-${id}`);
    const icon = btn.querySelector('.sec-icon');
    if (!body) return;
    const collapsed = body.style.display === 'none';
    body.style.display = collapsed ? '' : 'none';
    if (icon) icon.textContent = collapsed ? 'expand_less' : 'expand_more';
  });
}
