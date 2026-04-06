// ============================================================
// PROJECT DASHBOARD — single project view
// Layout ref:  new-ui/project_dashboard.html
// Logic ref:   ui/src/ui/ui_components/chat_component.py
//              ui/src/ui/ui_components/project_component.py
//              ui/src/ui/services/streaming_service.py
// ============================================================

import {
  loadProject, loadProjectSessions, loadSessionHistory,
  createSession, deleteSession, streamChat,
} from '../api.js';
import { fetchFileAsObjectUrl, fetchTextFile } from '../storage.js';
import { renderSidebar, bindSidebarEvents } from '../components/sidebar.js';
import { renderTopbar }                     from '../components/topbar.js';
import { appState }                         from '../state.js';
import { formatDate, timeAgo, toast, skeleton, uuid, escHtml } from '../utils.js';
import { marked }                           from 'marked';
import { chatLog }                          from '../logger.js';

// Configure marked: safe, breaks on newline
marked.setOptions({ breaks: true, gfm: true });
const md = (text) => marked.parse(text ?? '');

// ── Active streaming controller (cancel on navigation) ──────
let _streamController = null;

// ── Email store — avoids data-attribute encoding issues ───────
const _emailStore = new Map(); // key: email_id → email object

export async function renderProject(params) {
  const projectId = params.id;

  document.getElementById('app').innerHTML = `
    ${renderSidebar()}
    <div class="ml-64 min-h-screen bg-surface flex flex-col">
      ${renderTopbar({
        title: 'Loading...',
        breadcrumb: { label: 'Projects', href: '#/' },
      })}
      <div id="project-body" class="flex-1 flex">
        <div class="flex-1 p-10 space-y-4">${skeleton(5)}</div>
      </div>
    </div>`;

  bindSidebarEvents();

  try {
    const [data, sessions] = await Promise.all([
      loadProject(projectId),
      loadProjectSessions(projectId),
    ]);
    buildProjectShell(projectId, data, sessions);
  } catch (err) {
    document.getElementById('project-body').innerHTML =
      `<div class="p-10 text-error text-sm">${err.message}</div>`;
  }
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

function buildProjectShell(projectId, data, sessions) {
  const { factsheet, attachments, emails } = data;
  const title = factsheet.title ?? 'Untitled Project';

  // Update topbar title
  document.querySelector('#app header h2').textContent = title;

  document.getElementById('project-body').innerHTML = `
    <!-- Full-width scrollable factsheet -->
    <div class="flex-1 overflow-y-auto min-w-0" id="factsheet-panel">
      <div class="max-w-5xl mx-auto px-10 py-10 space-y-6">

        ${sec('background', 'Background', null,
          factsheet.background
            ? `<p class="text-sm text-on-surface font-body leading-relaxed whitespace-pre-line">${escHtml(factsheet.background)}</p>`
            : `<p class="text-sm text-on-surface-variant font-body italic">No background recorded.</p>`
        )}

        ${sec('timeline', 'Case Chronology', 'Key events and documentation milestones', buildTimelineInner(factsheet.events ?? []))}

        ${sec('parties', 'Parties & Claims', 'Identified legal entities and claims', buildPartiesClaims(factsheet.parties ?? [], factsheet.claims ?? []))}

        ${sec('factsheet', 'Factsheet', 'Deadlines, damages and documents', buildFactsheetInner(factsheet, attachments, emails))}

        <!-- Footer -->
        <div class="pt-4 border-t border-outline-variant/10 flex items-center justify-between text-[10px] text-on-surface-variant/40 font-body">
          <span class="font-mono">${projectId}</span>
          <span>Created ${formatDate(factsheet.created_at)}</span>
        </div>
      </div>
    </div>`;

  // Append viewer modal + chat drawer to app root
  const modal = document.createElement('div');
  modal.innerHTML = buildViewerModal();
  document.getElementById('app').appendChild(modal.firstElementChild);

  const drawer = document.createElement('div');
  drawer.innerHTML = buildChatDrawer(projectId, sessions);
  document.getElementById('app').appendChild(drawer.firstElementChild);

  bindProjectEvents(projectId, data, sessions);
  bindViewerEvents();
}

// ── Timeline ─────────────────────────────────────────────────

function buildTimelineInner(events) {
  if (!events.length) {
    return `<p class="text-on-surface-variant text-sm font-body py-4">No events recorded yet.</p>`;
  }
  return `
    <div class="relative overflow-x-auto pb-4 pt-2">
      <div class="min-w-[700px] relative px-2">
        <div class="absolute top-1/2 left-0 w-full h-[2px] bg-secondary/15 -translate-y-1/2 pointer-events-none"></div>
        <div class="flex justify-between relative gap-4">
          ${events.slice(0, 6).map((ev, i) => timelineItem(ev, i)).join('')}
        </div>
      </div>
    </div>`;
}

function timelineItem(ev, i) {
  const isAbove = i % 2 === 0;
  const isKey   = ev.is_key_event;
  const dot     = isKey
    ? `<div class="w-5 h-5 bg-primary rounded-full ring-[5px] ring-secondary-container/30 z-10 flex-shrink-0"></div>`
    : `<div class="w-3.5 h-3.5 bg-secondary rounded-full ring-4 ring-surface z-10 flex-shrink-0"></div>`;
  const card = `
    <div class="p-4 bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10 shadow-sm w-44
                ${isKey ? 'ring-secondary/20 shadow-lg' : ''}
                transition-all hover:-translate-y-0.5 hover:shadow-md">
      <span class="text-[9px] font-bold text-secondary uppercase block mb-1">${formatDate(ev.date ?? ev.event_date, { day: 'numeric', month: 'short', year: 'numeric' })}</span>
      <p class="text-xs font-semibold text-primary leading-tight line-clamp-3">${escHtml(ev.description ?? ev.event_description ?? '')}</p>
    </div>`;

  return isAbove
    ? `<div class="relative flex flex-col items-center group">${card}${dot}</div>`
    : `<div class="relative flex flex-col items-center group">${dot}${card}</div>`;
}

// ── Parties ───────────────────────────────────────────────────

function buildPartiesClaims(parties, claims) {
  const partyCards = parties.length
    ? parties.map(p => {
        const name    = p.legal_name ?? p.party_name ?? p.name ?? 'Unknown';
        const initial = name[0].toUpperCase();
        const role    = p.role ?? p.party_role ?? '';
        const type    = p.entity_type ? ` · ${p.entity_type}` : '';
        return `
          <div class="flex items-center gap-3 p-3 bg-surface-container rounded-xl
                      ring-1 ring-transparent hover:ring-secondary/20 transition-all">
            <div class="w-9 h-9 rounded-lg bg-primary-container flex items-center justify-center flex-shrink-0">
              <span class="text-on-primary text-sm font-bold">${escHtml(initial)}</span>
            </div>
            <div class="min-w-0">
              <p class="text-sm font-bold text-on-surface truncate">${escHtml(name)}</p>
              <p class="text-[10px] font-bold text-secondary uppercase tracking-tight">${escHtml(role + type)}</p>
            </div>
          </div>`;
      }).join('')
    : `<p class="text-on-surface-variant text-sm italic py-2">No parties recorded.</p>`;

  return `
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <div>
        <p class="text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-3">Parties</p>
        <div class="space-y-2">${partyCards}</div>
      </div>
      <div>${buildClaimsSection(claims)}</div>
    </div>`;
}

function buildClaimsSection(claims) {
  const items = claims.length
    ? claims.map(c => {
        const relief  = c.relief_sought    ? `<p class="text-[10px] text-secondary font-bold mt-1 uppercase tracking-wide">Relief: ${escHtml(c.relief_sought)}</p>` : '';
        const basis   = c.legal_basis      ? `<p class="text-[10px] text-on-surface-variant mt-0.5">${escHtml(c.legal_basis)}</p>` : '';
        const role    = c.party_role       ? `<span class="px-1.5 py-0.5 rounded bg-secondary-container/30 text-on-secondary-container text-[9px] font-bold uppercase">${escHtml(c.party_role)}</span>` : '';
        const cat     = c.category         ? `<span class="px-1.5 py-0.5 rounded bg-surface-container text-on-surface-variant text-[9px] font-bold uppercase">${escHtml(c.category)}</span>` : '';
        const desc    = c.factual_basis ?? c.defense ?? '';
        return `
          <div class="p-4 bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10">
            <div class="flex items-start justify-between gap-2 mb-1">
              <p class="text-sm font-semibold text-on-surface leading-snug">${escHtml(desc)}</p>
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

// ── Factsheet inner ───────────────────────────────────────────

function buildFactsheetInner(factsheet, attachments, emails) {
  const deadlines = factsheet.deadlines ?? [];
  const damages   = factsheet.damages   ?? [];

  return `
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">

      <!-- Deadlines -->
      <div>
        <p class="text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-3">Deadlines</p>
        <div class="space-y-2">
          ${deadlines.length
            ? deadlines.map(d => `
              <div class="flex items-center justify-between p-3.5 bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10">
                <div>
                  <p class="text-sm font-semibold text-on-surface">${escHtml(d.description ?? d.deadline_description ?? '')}</p>
                  <p class="text-[10px] text-on-surface-variant mt-0.5">${formatDate(d.date ?? d.deadline_date)}</p>
                </div>
                <span class="material-symbols-outlined text-[18px] text-tertiary-fixed-dim">event</span>
              </div>`).join('')
            : `<p class="text-on-surface-variant text-sm font-body py-4">No deadlines recorded.</p>`
          }
        </div>
      </div>

      <!-- Damages -->
      <div>
        <p class="text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-3">Damages</p>
        <div class="space-y-2">
          ${damages.length
            ? damages.map(d => {
                const desc   = d.basis ?? d.category ?? '';
                const amount = d.amount != null
                  ? `${d.currency ? escHtml(d.currency) + ' ' : ''}${escHtml(String(d.amount))}`
                  : '';
                return `
                <div class="flex items-center justify-between p-3.5 bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10">
                  <div class="min-w-0">
                    <p class="text-sm font-semibold text-on-surface">${escHtml(desc)}</p>
                    ${d.party_role ? `<p class="text-[10px] text-secondary font-bold uppercase mt-0.5">${escHtml(d.party_role)}</p>` : ''}
                  </div>
                  ${amount ? `<span class="text-sm font-bold text-secondary flex-shrink-0 ml-4 whitespace-nowrap">${amount}</span>` : ''}
                </div>`;
              }).join('')
            : `<p class="text-on-surface-variant text-sm font-body py-4">No damages recorded.</p>`
          }
        </div>
      </div>

      <!-- Attachments -->
      <div class="lg:col-span-2">
        <div class="flex items-center justify-between mb-4">
          <p class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Documents</p>
          <div class="flex gap-2">
            <span class="px-2.5 py-1 rounded-full bg-secondary-container/30 text-on-secondary-container text-xs font-bold">${attachments.length} files</span>
            <span class="px-2.5 py-1 rounded-full bg-surface-container text-on-surface-variant text-xs font-bold">${emails.length} emails</span>
          </div>
        </div>
        ${buildAttachmentsList(attachments, emails)}
      </div>
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
            <div id="viewer-email-headers" class="flex-shrink-0 px-8 pt-6 pb-4 bg-surface-container-low border-b border-outline-variant/10"></div>
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
  // Close on backdrop or button
  document.getElementById('viewer-close')?.addEventListener('click', closeViewer);
  document.getElementById('viewer-backdrop')?.addEventListener('click', closeViewer);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeViewer(); });

  // Attachment / email click
  document.addEventListener('click', async (e) => {
    const item = e.target.closest('.att-item');
    if (!item) return;

    const type = item.dataset.type;
    if (type === 'pdf')   await openPdfViewer(item);
    if (type === 'text')  await openTextViewer(item);
    if (type === 'email') openEmailViewer(item.dataset.emailId);
  });
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

function openEmailViewer(emailId) {
  const e = _emailStore.get(emailId);
  if (!e) return;

  const subject  = e.subject   ?? '(no subject)';
  const fromAddr = e.from_addr ?? '';
  const to       = Array.isArray(e.to) ? e.to.join(', ') : (e.to ?? '');
  const cc       = Array.isArray(e.cc) ? e.cc.join(', ') : (e.cc ?? '');
  const body     = e.body ?? '';
  const date     = e.date      ?? '';
  openViewer(subject, fromAddr, 'mail');
  document.getElementById('viewer-loading').classList.add('hidden');

  // Outlook-style header rows
  const row = (label, value) => value
    ? `<div class="flex gap-4 py-2 border-b border-outline-variant/10 last:border-0">
         <span class="w-16 flex-shrink-0 text-[10px] font-black uppercase tracking-wider text-on-surface-variant/60 pt-0.5">${label}</span>
         <span class="text-sm text-on-surface">${escHtml(value)}</span>
       </div>`
    : '';

  document.getElementById('viewer-email-headers').innerHTML = `
    <div class="mb-1">
      <h2 class="font-headline font-bold text-xl text-primary">${escHtml(subject)}</h2>
    </div>
    <div class="mt-3 bg-surface-container rounded-xl px-4 py-1 text-sm font-body">
      ${row('From', fromAddr)}
      ${row('To',   to)}
      ${cc ? row('Cc', cc) : ''}
      ${row('Date', date ? formatDate(date, { dateStyle: 'long', timeStyle: 'short' }) : '')}
    </div>`;

  // Body — plain textContent, same pattern as subject/from_addr
  const bodyEl = document.getElementById('viewer-email-body');
  bodyEl.style.whiteSpace = 'pre-wrap';
  bodyEl.style.fontSize   = '0.875rem';
  bodyEl.style.lineHeight = '1.6';
  bodyEl.textContent = body || '(no body)';

  document.getElementById('viewer-email').classList.remove('hidden');
}

// ── Chat drawer (floating, slide-in from right) ───────────────

function buildChatDrawer(projectId, sessions) {
  return `
    <!-- Floating chat button -->
    <button id="btn-chat-open"
      class="fixed bottom-6 right-6 z-[120] flex items-center gap-2 px-4 py-3 rounded-full
             bg-gradient-to-b from-primary to-primary-container text-on-primary shadow-lg
             hover:shadow-xl hover:scale-105 transition-all font-headline font-semibold text-sm">
      <span class="material-symbols-outlined text-[20px]" style="font-variation-settings:'FILL' 1">chat</span>
      Chat
    </button>

    <!-- Drawer -->
    <div id="chat-drawer"
      class="fixed right-0 z-[110] flex flex-col border-l border-outline-variant/10
             bg-surface-container-low shadow-[-8px_0_32px_rgba(0,0,0,0.1)]
             translate-x-full transition-transform duration-300"
      style="top:57px; bottom:0; width:480px">
      ${buildChatPanel(projectId, sessions)}
    </div>`;
}

function buildChatPanel(projectId, sessions) {
  const sessionOptions = sessions.map(s =>
    `<option value="${s.session_id}">${escHtml(s.title ?? 'Untitled Session')}</option>`
  ).join('');

  return `
    <!-- Session selector + controls -->
    <div class="p-3 border-b border-outline-variant/10 flex items-center gap-1.5 flex-shrink-0">
      <span class="material-symbols-outlined text-[18px] text-on-surface-variant flex-shrink-0">chat</span>
      <select id="session-select"
        class="flex-1 min-w-0 bg-transparent text-sm font-semibold text-on-surface outline-none cursor-pointer truncate">
        <option value="">— New session —</option>
        ${sessionOptions}
      </select>
      <button id="btn-new-session" title="New session"
        class="p-1.5 rounded-lg hover:bg-surface-container transition-colors flex-shrink-0">
        <span class="material-symbols-outlined text-[18px] text-on-surface-variant">add</span>
      </button>
      <button id="btn-delete-session" title="Delete session"
        class="p-1.5 rounded-lg hover:bg-error-container/40 transition-colors flex-shrink-0">
        <span class="material-symbols-outlined text-[18px] text-on-surface-variant hover:text-error">delete</span>
      </button>
      <button id="btn-chat-close" title="Close chat"
        class="p-1.5 rounded-lg hover:bg-surface-container transition-colors flex-shrink-0">
        <span class="material-symbols-outlined text-[18px] text-on-surface-variant">chevron_right</span>
      </button>
    </div>

    <!-- Messages -->
    <div id="chat-messages" class="flex-1 overflow-y-auto p-4 space-y-4 font-body text-sm">
      <div id="chat-welcome" class="flex flex-col items-center justify-center h-full py-12 text-center">
        <span class="material-symbols-outlined text-4xl text-on-surface-variant/30 mb-3">chat_bubble</span>
        <p class="text-on-surface-variant text-sm">Select a session or start a new conversation.</p>
      </div>
    </div>

    <!-- Input area -->
    <div class="p-4 border-t border-outline-variant/10">
      <!-- Model selector — format: provider_modelname (matches pick_llm in agent/utils.py) -->
      <div class="flex items-center gap-2 mb-3">
        <span class="material-symbols-outlined text-[14px] text-on-surface-variant">smart_toy</span>
        <select id="model-select" class="text-xs text-on-surface-variant bg-transparent outline-none cursor-pointer">
          <option value="google_gemini-2.5-flash" selected>Gemini 2.5 Flash</option>
          <option value="google_gemini-2.5-pro">Gemini 2.5 Pro</option>
          <option value="anthropic_claude-sonnet-4-6">Claude Sonnet 4.6</option>
          <option value="anthropic_claude-haiku-4-5">Claude Haiku 4.5</option>
          <option value="openai_gpt-5.3-chat-latest">GPT-5.3</option>
        </select>
      </div>

      <!-- Text input -->
      <div class="flex items-end gap-2">
        <textarea
          id="chat-input"
          rows="2"
          placeholder="Ask a question about this case..."
          class="flex-1 resize-none bg-surface-container ring-1 ring-outline-variant/20 focus:ring-2 focus:ring-secondary
                 rounded-xl px-3.5 py-2.5 text-sm font-body outline-none transition-all placeholder:text-on-surface-variant/40"
        ></textarea>
        <button id="btn-send"
          class="flex-shrink-0 p-2.5 rounded-xl bg-gradient-to-b from-primary to-primary-container text-on-primary
                 hover:opacity-90 transition-opacity disabled:opacity-40">
          <span class="material-symbols-outlined text-[20px]">send</span>
        </button>
      </div>

      <!-- File upload -->
      <div class="mt-2 flex items-center gap-2">
        <label for="file-upload" class="flex items-center gap-1.5 cursor-pointer text-xs text-on-surface-variant hover:text-secondary transition-colors">
          <span class="material-symbols-outlined text-[16px]">attach_file</span>
          Attach file
        </label>
        <input id="file-upload" type="file" class="hidden" multiple
               accept=".pdf,.txt,.eml,.csv,.xlsx,.pptx,.docx">
        <div id="file-chips" class="flex flex-wrap gap-1"></div>
      </div>
    </div>`;
}

// ── Chat state ────────────────────────────────────────────────

const chatState = {
  projectId:  null,
  sessionId:  null,
  messages:   [],       // { role, content, type, queryId }
  pendingFiles: [],     // File objects
  streaming:  false,
};

function bindProjectEvents(projectId, data, sessions) {
  chatState.projectId = projectId;
  chatState.sessions  = sessions;

  // Session selector
  document.getElementById('session-select')?.addEventListener('change', async (e) => {
    const sid = e.target.value;
    if (!sid) {
      chatState.sessionId = null;
      chatState.messages  = [];
      renderMessages();
      return;
    }
    chatState.sessionId = sid;
    await loadSession(sid);
  });

  // New session button
  document.getElementById('btn-new-session')?.addEventListener('click', async () => {
    await startNewSession(projectId);
  });

  // Delete session button
  document.getElementById('btn-delete-session')?.addEventListener('click', async () => {
    if (!chatState.sessionId) return;
    if (!confirm('Delete this session?')) return;
    try {
      await deleteSession(chatState.sessionId, projectId);
      chatState.sessionId = null;
      chatState.messages  = [];
      toast('Session deleted', 'success');
      // Refresh sessions list
      const updated = await loadProjectSessions(projectId);
      updateSessionSelect(updated);
      renderMessages();
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  // Chat drawer open/close
  const openDrawer  = () => document.getElementById('chat-drawer')?.classList.replace('translate-x-full', 'translate-x-0');
  const closeDrawer = () => document.getElementById('chat-drawer')?.classList.replace('translate-x-0', 'translate-x-full');

  document.getElementById('btn-chat-open')?.addEventListener('click', openDrawer);
  document.getElementById('btn-chat-close')?.addEventListener('click', closeDrawer);

  // Collapsible sections
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.sec-toggle');
    if (!btn) return;
    const id   = btn.dataset.sec;
    const body = document.getElementById(`sec-${id}`);
    const icon = btn.querySelector('.sec-icon');
    if (!body) return;
    const collapsed = body.style.display === 'none';
    body.style.display    = collapsed ? '' : 'none';
    if (icon) icon.textContent = collapsed ? 'expand_less' : 'expand_more';
  });

  // Send button
  document.getElementById('btn-send')?.addEventListener('click', () => sendMessage(projectId));

  // Enter key (Shift+Enter for newline)
  document.getElementById('chat-input')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(projectId);
    }
  });

  // File upload
  document.getElementById('file-upload')?.addEventListener('change', (e) => {
    chatState.pendingFiles = Array.from(e.target.files ?? []);
    renderFileChips();
  });
}

function updateSessionSelect(sessions) {
  const sel = document.getElementById('session-select');
  if (!sel) return;
  const opts = sessions.map(s =>
    `<option value="${s.session_id}" ${s.session_id === chatState.sessionId ? 'selected' : ''}>
      ${escHtml(s.title ?? 'Untitled Session')}
    </option>`
  ).join('');
  sel.innerHTML = `<option value="">— New session —</option>${opts}`;
}

async function startNewSession(projectId) {
  try {
    const session = await createSession(projectId, appState.user.id);
    chatState.sessionId = session.session_id;
    chatState.messages  = [];
    const updated = await loadProjectSessions(projectId);
    updateSessionSelect(updated);
    renderMessages();
    toast('New session started', 'success');
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function loadSession(sessionId) {
  const messagesEl = document.getElementById('chat-messages');
  if (messagesEl) messagesEl.innerHTML = `<div class="space-y-3">${skeleton(4)}</div>`;

  try {
    const { events } = await loadSessionHistory(sessionId);
    chatState.messages = events.map(ev => ({
      role:    ev.type,
      content: getEventContent(ev),
      type:    ev.type,
      queryId: ev.query_id,
      toolData: ev.type === 'tool_result' ? ev.data : null,
    }));
    renderMessages();
  } catch (err) {
    toast(err.message, 'error');
  }
}

function getEventContent(ev) {
  // ev.data kan være string (JSON), objekt, eller null
  let d = ev.data ?? {};
  if (typeof d === 'string') {
    try { d = JSON.parse(d); } catch { d = { content: d }; }
  }

  chatLog.debug({ type: ev.type, dataKeys: Object.keys(d) }, 'getEventContent');

  if (ev.type === 'human')       return d.content ?? '';
  if (ev.type === 'ai')          return d.token_stream ?? d.content ?? '';
  if (ev.type === 'tool_result') return d.tool_name ?? '';
  return '';
}

// ── Sending messages ─────────────────────────────────────────

async function sendMessage(projectId) {
  if (chatState.streaming) return;

  const inputEl  = document.getElementById('chat-input');
  const question = inputEl?.value.trim();
  if (!question) return;

  // Ensure session
  if (!chatState.sessionId) {
    await startNewSession(projectId);
    if (!chatState.sessionId) return;
  }

  inputEl.value = '';
  inputEl.disabled = true;
  document.getElementById('btn-send').disabled = true;

  const queryId = uuid();
  const model   = document.getElementById('model-select')?.value ?? 'gemini-2.5-flash';

  // Build file attachments (base64)
  const attachments = await buildAttachmentPayloads(chatState.pendingFiles, queryId);
  chatState.pendingFiles = [];
  renderFileChips();

  // Add human message to UI
  chatState.messages.push({ role: 'human', content: question, type: 'human', queryId });
  renderMessages();

  // Streaming AI message placeholder
  const aiMsg = { role: 'ai', content: '', type: 'ai', queryId, streaming: true };
  chatState.messages.push(aiMsg);
  chatState.streaming = true;
  renderMessages();

  const request = {
    question,
    attachments,
    session_id:  chatState.sessionId,
    llm_model:   model,
    query_id:    queryId,
    project_id:  projectId,
  };

  _streamController = streamChat(request, {
    onToken: (token) => {
      aiMsg.content += token;
      updateStreamingMessage(aiMsg);
    },
    onReasoning: (text) => {
      aiMsg.reasoning = (aiMsg.reasoning ?? '') + text;
      updateStreamingMessage(aiMsg);
    },
    onToolResult: (data) => {
      chatState.messages.push({ role: 'tool_result', content: `Tool: ${data.tool_name ?? ''}`, type: 'tool_result', toolData: data, queryId });
      renderMessages(true);
    },
    onDone: () => {
      aiMsg.streaming = false;
      chatState.streaming = false;
      inputEl.disabled = false;
      document.getElementById('btn-send').disabled = false;
      renderMessages();
    },
    onError: (err) => {
      aiMsg.content += `\n\n*Error: ${err.message}*`;
      aiMsg.streaming = false;
      chatState.streaming = false;
      inputEl.disabled = false;
      document.getElementById('btn-send').disabled = false;
      renderMessages();
      toast(err.message, 'error');
    },
  });
}

async function buildAttachmentPayloads(files, queryId) {
  return Promise.all(files.map(async (file) => {
    const bytes  = await file.arrayBuffer();
    const base64 = btoa(String.fromCharCode(...new Uint8Array(bytes)));
    const fileId = uuid();
    return {
      filename:  file.name,
      file_id:   fileId,
      content:   base64,
      path:      `${appState.user.id}/${chatState.sessionId}/${fileId}${file.name.slice(file.name.lastIndexOf('.'))}`,
      file_type: file.type,
      size:      file.size,
      query_id:  queryId,
    };
  }));
}

// ── Message rendering ─────────────────────────────────────────

function renderMessages(keepScroll = false) {
  const el = document.getElementById('chat-messages');
  if (!el) return;

  if (!chatState.messages.length) {
    el.innerHTML = `
      <div class="flex flex-col items-center justify-center h-full py-12 text-center">
        <span class="material-symbols-outlined text-4xl text-on-surface-variant/30 mb-3">chat_bubble</span>
        <p class="text-on-surface-variant text-sm">Ask a question to begin the conversation.</p>
      </div>`;
    return;
  }

  const wasAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
  el.innerHTML = chatState.messages.map(msg => renderMessage(msg)).join('');

  if (!keepScroll && (wasAtBottom || chatState.streaming)) {
    el.scrollTop = el.scrollHeight;
  }
}

function updateStreamingMessage(aiMsg) {
  const el = document.querySelector(`[data-query-id="${aiMsg.queryId}"].ai-message`);
  if (!el) { renderMessages(); return; }
  const contentEl = el.querySelector('.msg-content');
  if (contentEl) contentEl.innerHTML = md(aiMsg.content);
  const dotEl = el.querySelector('.streaming-dot');
  if (dotEl) dotEl.classList.toggle('hidden', !aiMsg.streaming);
  const messages = document.getElementById('chat-messages');
  if (messages) messages.scrollTop = messages.scrollHeight;
}


function renderMessage(msg) {
  if (msg.type === 'human') {
    return `
      <div class="flex justify-end">
        <div class="max-w-[85%] bg-primary-container text-on-primary rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed">
          ${escHtml(msg.content)}
        </div>
      </div>`;
  }

  if (msg.type === 'tool_result') {
    const toolName = msg.content || (msg.toolData?.tool_name ?? msg.toolData?.data?.tool_name ?? 'tool');
    return `
      <div class="flex items-start gap-2">
        <span class="material-symbols-outlined text-[16px] text-on-surface-variant mt-0.5 flex-shrink-0">build</span>
        <details class="flex-1 bg-surface-container rounded-xl overflow-hidden text-xs">
          <summary class="px-3 py-2 font-bold text-on-surface-variant cursor-pointer hover:bg-surface-container-high transition-colors list-none flex items-center gap-2">
            <span class="material-symbols-outlined text-[14px]">chevron_right</span>
            ${escHtml(toolName)}
          </summary>
          <div class="px-3 pb-3 text-on-surface-variant font-mono overflow-x-auto">
            <pre class="whitespace-pre-wrap text-[10px]">${escHtml(JSON.stringify(msg.toolData?.data ?? {}, null, 2))}</pre>
          </div>
        </details>
      </div>`;
  }

  // AI message
  return `
    <div class="flex items-start gap-2 ai-message" data-query-id="${msg.queryId ?? ''}">
      <div class="w-6 h-6 rounded-full bg-secondary-container flex items-center justify-center flex-shrink-0 mt-0.5">
        <span class="material-symbols-outlined text-[14px] text-secondary" style="font-variation-settings:'FILL' 1">smart_toy</span>
      </div>
      <div class="flex-1 min-w-0">
        ${msg.reasoning ? `
          <details class="mb-2 text-xs text-on-surface-variant">
            <summary class="cursor-pointer hover:text-primary transition-colors font-bold">Reasoning</summary>
            <div class="mt-1 font-body leading-relaxed opacity-70 prose prose-sm max-w-none">${md(msg.reasoning)}</div>
          </details>` : ''}
        <div class="msg-content prose prose-sm max-w-none text-on-surface font-body leading-relaxed
                    prose-headings:font-headline prose-headings:text-primary
                    prose-code:bg-surface-container prose-code:px-1 prose-code:rounded prose-code:text-xs
                    prose-pre:bg-surface-container prose-pre:rounded-xl prose-pre:text-xs">
          ${msg.content ? md(msg.content) : ''}
          <span class="streaming-dot ${msg.streaming ? '' : 'hidden'} inline-block w-1.5 h-3.5 bg-secondary animate-pulse rounded-sm ml-0.5 align-middle"></span>
        </div>
      </div>
    </div>`;
}

function renderFileChips() {
  const el = document.getElementById('file-chips');
  if (!el) return;
  el.innerHTML = chatState.pendingFiles.map((f, i) => `
    <div class="flex items-center gap-1 px-2 py-0.5 rounded-full bg-secondary-container/30 text-on-secondary-container text-[10px] font-semibold">
      ${escHtml(f.name.length > 20 ? f.name.slice(0,18) + '…' : f.name)}
      <button class="ml-1 hover:text-error" data-file-index="${i}">×</button>
    </div>`).join('');

  el.querySelectorAll('[data-file-index]').forEach(btn => {
    btn.addEventListener('click', () => {
      chatState.pendingFiles.splice(Number(btn.dataset.fileIndex), 1);
      renderFileChips();
    });
  });
}
