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
  streamProjectUpdate,
  insertProjectParty,
  insertProjectDeadline,
  insertProjectEvent,
  insertProjectClaim,
  insertProjectDamage,
} from '../api.js';
import { fetchFileAsObjectUrl, fetchTextFile } from '../storage.js';
import { renderProjectSidebar, bindProjectSidebarEvents } from '../components/sidebar_level2.js';
import { renderPipelineModal, openPipelineModal }  from '../components/pipeline_modal.js';
import { renderTopbar }                     from '../components/topbar.js';
import { formatDate, skeleton, escHtml, uuid, toast, arrayBufferToBase64, resolveFileType } from '../utils.js';
import { appState } from '../state.js';
import { initPopovers, registerItems }      from '../components/popovers.js';
import { marked }                           from 'marked';
import { chatLog }                          from '../logger.js';

// Configure marked: safe, breaks on newline
marked.setOptions({ breaks: true, gfm: true });
const md = (text) => marked.parse(text ?? '');

// ── Email store — avoids data-attribute encoding issues ───────
const _emailStore  = new Map(); // key: email_id → email object
const _attachStore = new Map(); // key: file_id  → attachment object
let   _viewerBound        = false; // prevents duplicate document listeners across navigations
let   _projectEventsBound = false; // same guard for project-page listeners
let   _activeProjectId    = null;  // current project, readable by modal handlers

export async function renderProject(params) {
  const projectId = params.id;
  _activeProjectId = projectId;

  // Clear stores so previous project's data doesn't linger
  _emailStore.clear();
  _attachStore.clear();

  document.getElementById('app').innerHTML = `
    ${renderProjectSidebar(projectId)}
    <div class="ml-64 min-h-screen bg-surface flex flex-col">
      ${renderTopbar({
        title: 'Loading...',
        breadcrumb: { label: 'Projects', href: '#/' },
      })}
      <div id="project-body" class="flex-1 flex">
        <div class="flex-1 p-10 space-y-4">${skeleton(5)}</div>
      </div>
    </div>`;

  bindProjectSidebarEvents({ onUpdate: () => _openUpdateModal(projectId) });

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

  // Shared docs promise — fetched once, used by both timeline and documents section
  const docsPromise = Promise.all([
    loadProjectAttachments(projectId),
    loadProjectEmails(projectId),
  ]);

  // Fire all sections in parallel
  Promise.all([loadProjectEvents(projectId), docsPromise])
    .then(([events, [attachments, emails]]) => {
      const el = document.getElementById('sec-timeline');
      if (el) {
        el.innerHTML = buildTimelineInner(events, attachments, emails);
        initTimeline(el);
      }
    })
    .catch(err => {
      const el = document.getElementById('sec-timeline');
      if (el) el.innerHTML = `<p class="text-error text-xs py-2">${err.message}</p>`;
    });

  loadSection('parties',   () => loadProjectParties(projectId),     buildPartiesInner);
  loadSection('claims',    () => loadProjectClaims(projectId),      buildClaimsSection);
  loadSection('deadlines', () => loadProjectDeadlines(projectId),   buildDeadlinesInner);
  loadSection('damages',   () => loadProjectDamages(projectId),     buildDamagesInner);

  // Documents section reuses the same fetch
  docsPromise
    .then(([attachments, emails]) => {
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
      <div class="max-w-7xl mx-auto px-10 py-10">

        <!-- Title + background -->
        <div class="mb-8">
          <h1 class="font-headline font-black text-3xl text-primary tracking-tight leading-tight">${escHtml(title)}</h1>
          <p class="text-xs text-on-surface-variant/40 font-mono mt-1.5">${projectId}</p>
          ${meta.background ? `
          <div class="mt-5 p-4 bg-surface-container-low/60 rounded-xl max-w-3xl">
            <div class="flex items-center gap-2 mb-2">
              <span class="material-symbols-outlined text-sm text-secondary">info</span>
              <h4 class="text-[10px] font-bold text-primary uppercase tracking-widest">Case Background</h4>
            </div>
            <p class="text-sm text-on-surface-variant leading-relaxed whitespace-pre-line">${escHtml(meta.background)}</p>
          </div>` : ''}
        </div>

        <!-- 2-column dashboard grid -->
        <div class="grid grid-cols-12 gap-8 mb-8">

          <!-- LEFT col (8): Timeline + Communication -->
          <div class="col-span-8 space-y-8">

            <!-- Case Timeline -->
            <div class="bg-surface-container-low rounded-xl overflow-hidden">
              <div class="flex items-center justify-between px-6 py-4 border-b border-outline-variant/5">
                <div>
                  <h3 class="font-headline font-bold text-base text-primary">Case Chronology</h3>
                  <p class="text-[10px] text-on-surface-variant mt-0.5">Scroll horizontally · click dots to expand</p>
                </div>
                <button data-add-type="event"
                  class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-secondary ring-1 ring-secondary/20 hover:bg-secondary/5 transition-colors">
                  <span class="material-symbols-outlined text-[14px]">add</span>Add Event
                </button>
              </div>
              <div class="px-6 pb-6 pt-3">
                <div id="sec-timeline">${sectionSkeleton}</div>
              </div>
            </div>

            <!-- Communication & Assets -->
            <div class="bg-surface-container-lowest rounded-xl overflow-hidden ring-1 ring-outline-variant/10">
              <div class="flex items-center justify-between px-6 py-4 border-b border-outline-variant/5">
                <h3 class="font-headline font-bold text-sm text-primary uppercase tracking-widest">Communication &amp; Assets</h3>
                <button class="text-xs font-bold text-secondary hover:underline">View All</button>
              </div>
              <div class="px-6 pb-6 pt-3">
                <div id="sec-documents">${sectionSkeleton}</div>
              </div>
            </div>

          </div>

          <!-- RIGHT col (4): Parties + Deadlines -->
          <div class="col-span-4 space-y-8">

            <!-- Parties -->
            <div class="bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10 p-6">
              <div class="flex items-center justify-between mb-5">
                <h3 class="font-headline font-bold text-sm text-primary uppercase tracking-widest">Parties</h3>
                <span class="material-symbols-outlined text-[20px] text-on-surface-variant/40 hover:text-secondary cursor-pointer transition-colors">search</span>
              </div>
              <div id="sec-parties" class="max-h-64 overflow-y-auto pr-1">${sectionSkeleton}</div>
              <button data-add-type="party" class="w-full mt-5 py-2 border border-dashed border-outline-variant rounded-lg text-xs font-bold text-on-surface-variant/50 hover:text-secondary hover:border-secondary transition-all">
                + Add Party
              </button>
            </div>

            <!-- Deadlines -->
            <div class="bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10 p-6">
              <div class="flex items-center justify-between mb-5">
                <h3 class="font-headline font-bold text-sm text-primary uppercase tracking-widest">Deadlines</h3>
                <span class="material-symbols-outlined text-[20px] text-on-surface-variant/40 hover:text-secondary cursor-pointer transition-colors">event</span>
              </div>
              <div id="sec-deadlines" class="max-h-64 overflow-y-auto pr-1">${sectionSkeleton}</div>
              <button data-add-type="deadline" class="w-full mt-5 py-2 border border-dashed border-outline-variant rounded-lg text-xs font-bold text-on-surface-variant/50 hover:text-secondary hover:border-secondary transition-all">
                + Add Deadline
              </button>
            </div>

          </div>
        </div>

        <!-- Full-width: Claims + Damages (collapsible) -->
        <div class="space-y-4">
          ${sec('claims',  'Claims',  null, sectionSkeleton)}
          ${sec('damages', 'Damages', null, sectionSkeleton)}
        </div>

        <div class="mt-8 pt-4 border-t border-outline-variant/10 text-[10px] text-on-surface-variant/30 font-body">
          Created ${formatDate(meta.created_at)}
        </div>
      </div>
    </div>`;

  // Append viewer modal + update modal
  const modal = document.createElement('div');
  modal.innerHTML = buildViewerModal();
  document.getElementById('app').appendChild(modal.firstElementChild);

  const updateModalEl = document.createElement('div');
  updateModalEl.innerHTML = renderPipelineModal({
    id:          'update',
    icon:        'sync',
    title:       'Update Project',
    description: 'Add new documents to analyse',
    runLabel:    'Update Project',
  });
  document.getElementById('app').appendChild(updateModalEl.firstElementChild);

  if (!document.getElementById('add-entity-modal')) {
    const addModal = document.createElement('div');
    addModal.innerHTML = buildAddModal();
    document.getElementById('app').appendChild(addModal.firstElementChild);
  }

  // Init entity popovers (idempotent)
  initPopovers();

  bindProjectEvents(projectId);
  bindViewerEvents();
}

// ── Timeline (horizontal, scrollable) ────────────────────────

function buildTimelineInner(events, attachments = [], emails = []) {
  // Register attachments and emails in stores so the viewer can open them
  attachments.forEach(a => { if (a.file_id) _attachStore.set(a.file_id, a); });
  emails.forEach(e => {
    const id = e.email_id ?? e.message_id;
    if (id) _emailStore.set(id, e);
  });

  if (events.length) registerItems('event', events, 'event_id');

  if (!events.length && !attachments.length && !emails.length) {
    return `<p class="text-on-surface-variant text-sm font-body py-4">No events recorded yet.</p>`;
  }

  // Determine date range across all item types
  const allTs = [
    ...events.map(e => e.event_start_date),
    ...attachments.map(a => a.file_date ?? a.created_at),
    ...emails.map(e => e.date),
  ].filter(Boolean).map(d => +new Date(d)).filter(ts => !isNaN(ts));

  if (!allTs.length) {
    return `<p class="text-on-surface-variant text-sm font-body py-4">No dated items found.</p>`;
  }

  const minTs      = Math.min(...allTs);
  const maxTs      = Math.max(...allTs);
  const spanMs     = maxTs - minTs || 30 * 24 * 3600 * 1000;
  const rangeStart = minTs - spanMs * 0.06;
  const rangeEnd   = maxTs + spanMs * 0.14;
  const totalRange = rangeEnd - rangeStart;

  const toLeft = (dateVal) => {
    if (!dateVal) return null;
    const ts = +new Date(dateVal);
    if (isNaN(ts)) return null;
    return Math.max(2, Math.min(98, ((ts - rangeStart) / totalRange) * 100));
  };

  const isHigh  = e => (e.significance ?? '').toLowerCase() === 'high';
  const byDate  = (a, b) => +new Date(a.event_start_date || 0) - +new Date(b.event_start_date || 0);
  const highEvents = [...events].filter(isHigh).sort(byDate);
  const lowEvents  = [...events].filter(e => !isHigh(e)).sort(byDate);

  const months    = Math.ceil(spanMs / (30 * 24 * 3600 * 1000));
  const minWidth  = Math.max(1600, months * 110);
  const CONTAINER_H = 500;
  const AXIS_PCT    = 50; // axis at vertical midpoint

  // Center of mass — average left% across all dated items (used for auto-scroll)
  const allLeftPcts = [
    ...events.map(e => toLeft(e.event_start_date)),
    ...attachments.map(a => toLeft(a.file_date ?? a.created_at)),
    ...emails.map(e => toLeft(e.date)),
  ].filter(v => v !== null);
  const centerPct = allLeftPcts.length
    ? allLeftPcts.reduce((s, v) => s + v, 0) / allLeftPcts.length
    : 50;

  let html = '';

  // ── Duration spans (events with both start + end date) ───────
  // Rendered as horizontal bars in a Gantt-like strip near the axis.
  // Lane algorithm: assign each event to the lowest lane that doesn't overlap.
  const spanEvents = [...highEvents, ...lowEvents]
    .filter(ev => ev.event_start_date && ev.event_end_date);
  const laneEnds = []; // laneEnds[i] = rightmost end-% of last event in lane i
  spanEvents.forEach(ev => {
    const leftPct  = toLeft(ev.event_start_date);
    const rightPct = toLeft(ev.event_end_date);
    if (leftPct === null || rightPct === null || rightPct <= leftPct + 0.4) return;

    let lane = 0;
    while (lane < laneEnds.length && laneEnds[lane] > leftPct + 0.5) lane++;
    if (lane === laneEnds.length) laneEnds.push(0);
    laneEnds[lane] = rightPct;

    const widthPct = rightPct - leftPct;
    const LANE_H   = 9;
    const LANE_GAP = 4;
    const yTop     = 10 + lane * (LANE_H + LANE_GAP); // px from container top
    const barColor = isHigh(ev)
      ? 'background:rgba(62,96,142,0.55);'
      : 'background:rgba(198,198,208,0.6);';
    const name     = escHtml(ev.event_name ?? ev.description ?? '');

    html += `
      <div class="absolute cursor-pointer popover-item group"
           style="left:${leftPct}%; width:${widthPct}%; top:${yTop}px; height:${LANE_H}px; border-radius:999px; overflow:hidden;"
           data-popover-type="event" data-popover-id="${escHtml(ev.event_id)}"
           title="${name}">
        <div class="w-full h-full group-hover:brightness-75 transition-all" style="${barColor} border-radius:999px;"></div>
        ${widthPct > 4 ? `<span class="absolute inset-0 flex items-center px-2 text-[8px] font-bold text-on-surface-variant/80 truncate pointer-events-none">${name}</span>` : ''}
      </div>`;
  });

  // ── High-significance events (full cards, alternating above/below axis)
  highEvents.forEach((ev, i) => {
    const left = toLeft(ev.event_start_date);
    if (left === null) return;
    const above   = i % 2 === 0;
    const dateStr = ev.event_start_date ? formatDate(ev.event_start_date, { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
    const endStr  = ev.event_end_date   ? ` – ${formatDate(ev.event_end_date, { day: 'numeric', month: 'short', year: 'numeric' })}` : '';
    const name    = escHtml(ev.event_name ?? ev.description ?? '');
    const desc    = (ev.event_name && ev.description)
      ? `<p class="text-[9px] text-on-surface-variant mt-1 leading-relaxed line-clamp-2">${escHtml(ev.description)}</p>` : '';
    const badges  = [
      ev.disputed ? `<span class="px-1 py-0.5 rounded bg-error-container text-error text-[8px] font-bold uppercase">Disputed</span>` : '',
      ev.category ? `<span class="px-1 py-0.5 rounded bg-surface-container text-on-surface-variant text-[8px] font-bold uppercase">${escHtml(ev.category)}</span>` : '',
    ].filter(Boolean).join('');

    const card = `
      <div class="w-48 p-3 bg-surface-container-lowest rounded-xl shadow-md border border-secondary/20
                  cursor-pointer popover-item hover:shadow-lg hover:-translate-y-0.5 transition-all flex-shrink-0"
           data-popover-type="event" data-popover-id="${escHtml(ev.event_id)}">
        <p class="text-[9px] font-black text-secondary uppercase mb-0.5">${dateStr}${endStr}</p>
        <h4 class="text-[11px] font-bold text-on-surface leading-tight">${name}</h4>
        ${desc}
        ${badges ? `<div class="flex flex-wrap gap-0.5 mt-1.5">${badges}</div>` : ''}
      </div>`;
    const stem = `<div class="w-px flex-shrink-0 bg-gradient-to-b from-secondary/50 to-secondary/20" style="height:40px;"></div>`;
    const dot  = `<div class="w-4 h-4 rounded-full bg-primary border-2 border-surface shadow-lg z-20 flex-shrink-0"></div>`;

    if (above) {
      html += `
        <div class="absolute flex flex-col items-center" style="left:${left}%; bottom:${100 - AXIS_PCT}%; transform:translateX(-50%);">
          ${card}${stem}${dot}
        </div>`;
    } else {
      html += `
        <div class="absolute flex flex-col items-center" style="left:${left}%; top:${AXIS_PCT}%; transform:translateX(-50%);">
          ${dot}${stem}${card}
        </div>`;
    }
  });

  // ── Low-significance events (dots on axis, click to expand card)
  lowEvents.forEach((ev, i) => {
    const left = toLeft(ev.event_start_date);
    if (left === null) return;
    const above   = i % 2 === 0;
    const dateStr = ev.event_start_date ? formatDate(ev.event_start_date, { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
    const name    = escHtml(ev.event_name ?? ev.description ?? '');

    const card = `
      <div class="tl-dot-card hidden w-44 p-2.5 bg-surface-container rounded-xl shadow-lg border border-outline-variant/20 flex-shrink-0
                  cursor-pointer popover-item"
           data-popover-type="event" data-popover-id="${escHtml(ev.event_id)}">
        <p class="text-[9px] font-black text-on-surface-variant/70 uppercase mb-0.5">${dateStr}</p>
        <p class="text-[10px] font-bold text-on-surface leading-tight">${name}</p>
      </div>`;
    const gap = `<div class="w-px flex-shrink-0 bg-outline-variant/30" style="height:14px;"></div>`;
    const dot = `<div class="w-2.5 h-2.5 rounded-full bg-outline-variant border border-surface cursor-pointer tl-dot
                             hover:bg-secondary hover:scale-150 transition-all flex-shrink-0 z-20"></div>`;

    if (above) {
      html += `
        <div class="absolute tl-dot-wrap flex flex-col items-center" style="left:${left}%; bottom:${100 - AXIS_PCT}%; transform:translateX(-50%);">
          ${card}${gap}${dot}
        </div>`;
    } else {
      html += `
        <div class="absolute tl-dot-wrap flex flex-col items-center" style="left:${left}%; top:${AXIS_PCT}%; transform:translateX(-50%);">
          ${dot}${gap}${card}
        </div>`;
    }
  });

  // ── Email dots (green, above axis, click to expand then opens viewer)
  emails.forEach((e) => {
    const id   = e.email_id ?? e.message_id;
    if (!id) return;
    const left = toLeft(e.date);
    if (left === null) return;

    html += `
      <div class="absolute tl-dot-wrap flex flex-col items-center" style="left:${left}%; bottom:${100 - AXIS_PCT + 3}%; transform:translateX(-50%);">
        <div class="tl-dot-card hidden w-48 p-2.5 bg-green-50 rounded-xl shadow-lg border border-green-200 flex-shrink-0 att-item cursor-pointer"
             data-type="email" data-email-id="${escHtml(id)}">
          <div class="flex items-center gap-1.5 mb-0.5">
            <span class="material-symbols-outlined text-green-500" style="font-size:13px;">mail</span>
            <span class="text-[10px] font-bold text-green-700 truncate">${escHtml(e.subject ?? 'Email')}</span>
          </div>
          <p class="text-[9px] text-green-600">${formatDate(e.date)}</p>
          ${e.from_addr ? `<p class="text-[9px] text-green-500/80 truncate mt-0.5">${escHtml(e.from_addr)}</p>` : ''}
        </div>
        <div class="w-px flex-shrink-0 bg-green-400/50" style="height:18px;"></div>
        <div class="w-3 h-3 rounded-full bg-green-500 border-2 border-surface shadow tl-dot cursor-pointer hover:scale-125 transition-transform flex-shrink-0 z-20"></div>
      </div>`;
  });

  // ── Attachment dots (blue, below axis, click to expand then opens viewer)
  attachments.forEach((a) => {
    const left  = toLeft(a.file_date ?? a.created_at);
    if (left === null) return;
    const vtype = fileViewType(a.filename ?? '', a.file_type ?? '');
    const ext   = (a.filename ?? '').slice((a.filename ?? '').lastIndexOf('.')).toLowerCase();
    const isMd  = ext === '.md' || ext === '.markdown';

    html += `
      <div class="absolute tl-dot-wrap flex flex-col items-center" style="left:${left}%; top:${AXIS_PCT + 3}%; transform:translateX(-50%);">
        <div class="w-3 h-3 rounded-full bg-blue-500 border-2 border-surface shadow tl-dot cursor-pointer hover:scale-125 transition-transform flex-shrink-0 z-20"></div>
        <div class="w-px flex-shrink-0 bg-blue-400/50" style="height:18px;"></div>
        <div class="tl-dot-card hidden w-48 p-2.5 bg-blue-50 rounded-xl shadow-lg border border-blue-200 flex-shrink-0
                    ${vtype ? 'att-item cursor-pointer' : 'opacity-70'}"
             data-type="${vtype ?? ''}" data-path="${escHtml(a.path ?? '')}"
             data-name="${escHtml(a.filename ?? '')}" data-file-type="${escHtml(a.file_type ?? '')}"
             data-is-markdown="${isMd}">
          <div class="flex items-center gap-1.5 mb-0.5">
            <span class="material-symbols-outlined text-blue-500" style="font-size:13px;">attachment</span>
            <span class="text-[10px] font-bold text-blue-700 truncate">${escHtml(a.filename ?? 'Attachment')}</span>
          </div>
          <p class="text-[9px] text-blue-600">${formatDate(a.file_date ?? a.created_at)}</p>
        </div>
      </div>`;
  });

  // ── Legend + zoom controls
  const legend = `
    <div class="flex items-center gap-4 px-5 pt-4 pb-3 border-b border-outline-variant/10 flex-shrink-0 flex-wrap gap-y-1.5">
      <div class="flex items-center gap-1.5">
        <span class="inline-block w-2.5 h-2.5 rounded-full bg-primary flex-shrink-0"></span>
        <span class="text-[10px] font-bold text-on-surface-variant uppercase tracking-wide">Key Events</span>
      </div>
      <div class="flex items-center gap-1.5">
        <span class="inline-block w-2.5 h-2.5 rounded-full bg-outline-variant flex-shrink-0"></span>
        <span class="text-[10px] font-bold text-on-surface-variant uppercase tracking-wide">Other Events</span>
      </div>
      <div class="flex items-center gap-1.5">
        <span class="inline-block w-2.5 h-2.5 rounded-full bg-green-500 flex-shrink-0"></span>
        <span class="text-[10px] font-bold text-on-surface-variant uppercase tracking-wide">Emails</span>
      </div>
      <div class="flex items-center gap-1.5">
        <span class="inline-block w-2.5 h-2.5 rounded-full bg-blue-500 flex-shrink-0"></span>
        <span class="text-[10px] font-bold text-on-surface-variant uppercase tracking-wide">Attachments</span>
      </div>
      <!-- Zoom controls -->
      <div class="ml-auto flex items-center gap-1">
        <button class="tl-zoom-btn tl-zoom-out w-7 h-7 flex items-center justify-center rounded-lg bg-surface-container hover:bg-surface-container-high transition-colors text-on-surface-variant">
          <span class="material-symbols-outlined" style="font-size:16px;">remove</span>
        </button>
        <span class="tl-zoom-label text-[10px] font-mono text-on-surface-variant w-10 text-center">—</span>
        <button class="tl-zoom-btn tl-zoom-in w-7 h-7 flex items-center justify-center rounded-lg bg-surface-container hover:bg-surface-container-high transition-colors text-on-surface-variant">
          <span class="material-symbols-outlined" style="font-size:16px;">add</span>
        </button>
        <button class="tl-zoom-btn tl-zoom-reset ml-1 px-2 h-7 flex items-center rounded-lg bg-surface-container hover:bg-surface-container-high transition-colors text-on-surface-variant text-[10px] font-bold uppercase tracking-wide">
          Fit
        </button>
      </div>
    </div>`;

  return `
    <div class="rounded-xl bg-surface-container-lowest border border-outline-variant/10 shadow-sm -mx-2 flex flex-col">
      ${legend}
      <div class="tl-scroll overflow-x-auto" data-tl-center="${centerPct.toFixed(2)}">
        <div class="tl-inner relative"
             data-tl-base-width="${minWidth}"
             data-tl-range-start="${rangeStart}"
             data-tl-total-range="${totalRange}"
             style="min-width:${minWidth}px; height:${CONTAINER_H}px;">
          <!-- Axis line -->
          <div class="absolute left-0 right-0" style="top:${AXIS_PCT}%; height:2px; background:rgba(198,198,208,0.35);"></div>
          <!-- All timeline items (spans, events, dots) -->
          ${html}
          <!-- Date ruler — populated dynamically by initTimeline -->
          <div class="tl-tick-ruler absolute left-0 right-0" style="height:28px; bottom:4px;"></div>
        </div>
      </div>
    </div>`;
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
    <div class="space-y-3">${items}</div>
    <button data-add-type="claim" class="w-full mt-4 py-2 border border-dashed border-outline-variant rounded-lg text-xs font-bold text-on-surface-variant/50 hover:text-secondary hover:border-secondary transition-all">
      + Add Claim
    </button>`;
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
  const addBtn = `<button data-add-type="damage" class="w-full mt-4 py-2 border border-dashed border-outline-variant rounded-lg text-xs font-bold text-on-surface-variant/50 hover:text-secondary hover:border-secondary transition-all">+ Add Damage</button>`;
  if (!damages.length) return `<p class="text-on-surface-variant text-sm italic py-2">No damages recorded.</p>${addBtn}`;
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
  </div>${addBtn}`;
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

// ── Add entity modal ──────────────────────────────────────────

function buildAddModal() {
  return `
    <div id="add-entity-modal" class="hidden fixed inset-0 z-[250] flex items-center justify-center p-4">
      <div id="add-entity-backdrop" class="absolute inset-0 bg-black/30 backdrop-blur-sm"></div>
      <div class="relative bg-surface-container-lowest rounded-2xl shadow-[0_32px_80px_-16px_rgba(0,0,0,0.2)] w-full max-w-md ring-1 ring-outline-variant/10 overflow-hidden">
        <div class="flex items-center justify-between px-6 py-4 border-b border-outline-variant/10">
          <h2 id="add-modal-title" class="font-headline font-bold text-base text-primary"></h2>
          <button id="add-modal-close" class="p-1.5 rounded-lg hover:bg-surface-container text-on-surface-variant transition-colors">
            <span class="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>
        <div class="p-6 space-y-4 overflow-y-auto max-h-[65vh]">
          <div id="add-modal-fields" class="space-y-4"></div>
          <div id="add-modal-error" class="hidden text-sm text-error bg-error-container/40 rounded-lg px-3.5 py-2.5"></div>
        </div>
        <div class="px-6 py-4 border-t border-outline-variant/10 flex gap-3">
          <button id="add-modal-cancel"
            class="flex-1 px-4 py-2.5 rounded-lg bg-surface-container text-on-surface font-headline font-semibold text-sm hover:bg-surface-container-high transition-colors">
            Cancel
          </button>
          <button id="add-modal-submit"
            class="flex-1 px-4 py-2.5 rounded-lg bg-gradient-to-b from-primary to-primary-container text-on-primary font-headline font-semibold text-sm hover:opacity-90 transition-opacity">
            Add
          </button>
        </div>
      </div>
    </div>`;
}

const ADD_FIELDS = {
  party: [
    { id: 'legal_name',       label: 'Legal Name',               type: 'text',     required: true,  placeholder: 'e.g. Acme Corp AS' },
    { id: 'role',             label: 'Role',                     type: 'text',     required: false, placeholder: 'e.g. Plaintiff, Defendant' },
    { id: 'entity_type',      label: 'Entity Type',              type: 'select',   required: false, options: ['', 'Individual', 'Company', 'Government', 'Other'] },
    { id: 'role_description', label: 'Description',              type: 'textarea', required: false, placeholder: 'Optional description…' },
  ],
  deadline: [
    { id: 'title',         label: 'Title',         type: 'text',          required: true,  placeholder: 'e.g. Response deadline' },
    { id: 'deadline_date', label: 'Deadline Date', type: 'datetime-local', required: true  },
    { id: 'description',   label: 'Description',   type: 'textarea',      required: false, placeholder: 'Optional details…' },
    { id: 'party_role',    label: 'Party Role',    type: 'text',          required: false, placeholder: 'e.g. Defendant' },
  ],
  event: [
    { id: 'event_name',       label: 'Event Name',   type: 'text',          required: true,  placeholder: 'e.g. Contract signed' },
    { id: 'event_start_date', label: 'Start Date',   type: 'datetime-local', required: true  },
    { id: 'event_end_date',   label: 'End Date',     type: 'datetime-local', required: false },
    { id: 'category',         label: 'Category',     type: 'text',          required: false, placeholder: 'e.g. Contract, Litigation' },
    { id: 'description',      label: 'Description',  type: 'textarea',      required: false, placeholder: 'Optional description…' },
    { id: 'disputed',         label: 'Disputed',     type: 'checkbox',      required: false },
  ],
  claim: [
    { id: 'title',         label: 'Title',         type: 'text',     required: true,  placeholder: 'e.g. Breach of contract' },
    { id: 'factual_basis', label: 'Factual Basis', type: 'textarea', required: false, placeholder: 'Facts supporting the claim…' },
    { id: 'legal_basis',   label: 'Legal Basis',   type: 'text',     required: false, placeholder: 'e.g. §10-1 avtaleloven' },
    { id: 'party_role',    label: 'Party Role',    type: 'text',     required: false, placeholder: 'e.g. Plaintiff' },
    { id: 'relief_sought', label: 'Relief Sought', type: 'text',     required: false, placeholder: 'e.g. Damages, Injunction' },
    { id: 'category',      label: 'Category',      type: 'text',     required: false, placeholder: 'e.g. Contractual, Tort' },
  ],
  damage: [
    { id: 'title',      label: 'Title',        type: 'text',     required: true,  placeholder: 'e.g. Loss of revenue' },
    { id: 'basis',      label: 'Basis',        type: 'textarea', required: false, placeholder: 'Describe the basis…' },
    { id: 'amount',     label: 'Amount',       type: 'number',   required: false, placeholder: '0' },
    { id: 'currency',   label: 'Currency',     type: 'text',     required: false, placeholder: 'e.g. NOK' },
    { id: 'party_role', label: 'Party Role',   type: 'text',     required: false, placeholder: 'e.g. Claimant' },
    { id: 'category',   label: 'Category',     type: 'text',     required: false, placeholder: 'e.g. Economic, Non-economic' },
  ],
};

function _fieldHTML(f) {
  const base = 'w-full bg-surface-container ring-1 ring-outline-variant/20 focus:ring-2 focus:ring-secondary rounded-lg px-3.5 py-2.5 text-sm font-body outline-none transition-all';
  const label = `<label for="af-${f.id}" class="block text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-1.5">${f.label}${f.required ? ' <span class="text-error">*</span>' : ''}</label>`;
  if (f.type === 'textarea')
    return `<div>${label}<textarea id="af-${f.id}" rows="3" placeholder="${f.placeholder ?? ''}" class="${base} resize-none"></textarea></div>`;
  if (f.type === 'select')
    return `<div>${label}<select id="af-${f.id}" class="${base} cursor-pointer">${f.options.map(o => `<option value="${o}">${o || '— Select —'}</option>`).join('')}</select></div>`;
  if (f.type === 'checkbox')
    return `<div class="flex items-center gap-3"><input type="checkbox" id="af-${f.id}" class="accent-secondary w-4 h-4"><label for="af-${f.id}" class="text-sm font-semibold text-on-surface">${f.label}</label></div>`;
  return `<div>${label}<input id="af-${f.id}" type="${f.type}" placeholder="${f.placeholder ?? ''}" class="${base}" ${f.required ? 'required' : ''}></div>`;
}

function openAddModal(type) {
  const modal = document.getElementById('add-entity-modal');
  if (!modal) return;
  const fields = ADD_FIELDS[type];
  if (!fields) return;

  const titles = { party: 'Add Party', deadline: 'Add Deadline', event: 'Add Event', claim: 'Add Claim', damage: 'Add Damage' };
  document.getElementById('add-modal-title').textContent   = titles[type] ?? 'Add';
  document.getElementById('add-modal-fields').innerHTML    = fields.map(_fieldHTML).join('');
  document.getElementById('add-modal-error').classList.add('hidden');

  const btn = document.getElementById('add-modal-submit');
  btn.disabled    = false;
  btn.textContent = 'Add';

  modal.classList.remove('hidden');
  document.querySelector('#add-entity-modal input, #add-entity-modal textarea')?.focus();

  // Close handlers
  const close = () => modal.classList.add('hidden');
  document.getElementById('add-modal-close')?.addEventListener('click', close, { once: true });
  document.getElementById('add-modal-cancel')?.addEventListener('click', close, { once: true });
  document.getElementById('add-entity-backdrop')?.addEventListener('click', close, { once: true });

  // Submit
  const newBtn = btn.cloneNode(true);
  btn.parentNode.replaceChild(newBtn, btn);
  newBtn.addEventListener('click', async () => {
    const errorEl = document.getElementById('add-modal-error');
    errorEl.classList.add('hidden');

    // Collect field values
    const data = {};
    for (const f of fields) {
      const el = document.getElementById(`af-${f.id}`);
      if (!el) continue;
      if (f.type === 'checkbox') {
        data[f.id] = el.checked;
      } else if (f.type === 'number') {
        data[f.id] = el.value ? Number(el.value) : null;
      } else {
        data[f.id] = el.value.trim() || null;
      }
      if (f.required && !data[f.id] && f.type !== 'checkbox') {
        errorEl.textContent = `${f.label} is required.`;
        errorEl.classList.remove('hidden');
        return;
      }
    }

    newBtn.disabled    = true;
    newBtn.textContent = 'Saving…';

    try {
      const userId = appState.user?.id;
      const pid    = _activeProjectId;
      const insertFns = {
        party:    () => insertProjectParty(pid, userId, data),
        deadline: () => insertProjectDeadline(pid, userId, data),
        event:    () => insertProjectEvent(pid, userId, data),
        claim:    () => insertProjectClaim(pid, userId, data),
        damage:   () => insertProjectDamage(pid, userId, data),
      };
      await insertFns[type]();
      toast(`${titles[type]} added`, 'success');
      modal.classList.add('hidden');
      await reloadEntitySection(type, pid);
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.remove('hidden');
      newBtn.disabled    = false;
      newBtn.textContent = 'Add';
    }
  });
}

async function reloadEntitySection(type, projectId) {
  if (type === 'event') {
    const el = document.getElementById('sec-timeline');
    if (!el) return;
    try {
      const [events, [attachments, emails]] = await Promise.all([
        loadProjectEvents(projectId),
        Promise.all([loadProjectAttachments(projectId), loadProjectEmails(projectId)]),
      ]);
      el.innerHTML = buildTimelineInner(events, attachments, emails);
      initTimeline(el);
    } catch (err) { toast(err.message, 'error'); }
    return;
  }
  const cfg = {
    party:    { id: 'parties',   fetch: () => loadProjectParties(projectId),   render: buildPartiesInner },
    deadline: { id: 'deadlines', fetch: () => loadProjectDeadlines(projectId), render: buildDeadlinesInner },
    claim:    { id: 'claims',    fetch: () => loadProjectClaims(projectId),    render: buildClaimsSection },
    damage:   { id: 'damages',   fetch: () => loadProjectDamages(projectId),   render: buildDamagesInner },
  }[type];
  if (!cfg) return;
  const el = document.getElementById(`sec-${cfg.id}`);
  if (!el) return;
  try {
    const data = await cfg.fetch();
    el.innerHTML = cfg.render(data);
  } catch (err) { toast(err.message, 'error'); }
}

// ── Update Project modal ──────────────────────────────────────

function _openUpdateModal(projectId) {
  openPipelineModal('update', {
    onRun: async ({ files, question }, { logLine, setError, setDone, setAbort, onChunk }) => {
      const queryId = uuid();

      let attachments;
      try {
        attachments = await Promise.all(files.map(async (file) => {
          const bytes  = await file.arrayBuffer();
          const b64    = arrayBufferToBase64(bytes);
          const fileId = uuid();
          return {
            filename:  file.name,
            file_id:   fileId,
            content:   b64,
            path:      `${appState.user.id}/${projectId}/${fileId}${file.name.slice(file.name.lastIndexOf('.'))}`,
            file_type: resolveFileType(file),
            size:      file.size,
            query_id:  queryId,
          };
        }));
      } catch (err) {
        setError(`File read error: ${err.message}`);
        return;
      }

      const ctrl = streamProjectUpdate(
        {
          question:    question || 'Update project with new documents.',
          attachments,
          session_id:  uuid(),
          llm_model:   'google_gemini-2.5-flash',
          query_id:    queryId,
          project_id:  projectId,
        },
        {
          onChunk:      (e) => onChunk(e),
          onToken:      (t) => console.log('onToken:', t),
          onToolResult: (r) => console.log('onToolResult:', r),
          onDone:  ()       => {
            setDone('✅ Project updated! Reloading...');
            toast('Project updated', 'success');
            setTimeout(() => {
              cache.clear();
              renderProject(projectId);
            }, 1200);
          },
          onError: (err)    => setError(err.message),
        },
      );
      setAbort(ctrl);
    },
  });
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


// ── Project events (collapsible sections + timeline dots) ─────

function bindProjectEvents(_projectId) {
  // Guard: only attach document listeners once across all navigations
  if (_projectEventsBound) return;
  _projectEventsBound = true;

  // Add entity buttons (delegated — works for dynamically re-rendered sections)
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-add-type]');
    if (!btn || e.target.closest('#add-entity-modal')) return;
    openAddModal(btn.dataset.addType);
  });

  // Entity deleted via popover — reload the affected section
  document.addEventListener('entity-deleted', async (e) => {
    const { type, projectId } = e.detail;
    if (!projectId || !document.getElementById('factsheet-panel')) return;
    await reloadEntitySection(type, projectId);
  });

  // Collapsible sections
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

  // Timeline dot single-click → toggle preview card
  document.addEventListener('click', (e) => {
    const dot = e.target.closest('.tl-dot');
    if (dot) {
      const wrap = dot.closest('.tl-dot-wrap');
      if (!wrap) return;
      const card = wrap.querySelector('.tl-dot-card');
      if (!card) return;
      document.querySelectorAll('.tl-dot-card:not(.hidden)').forEach(c => {
        if (c !== card) c.classList.add('hidden');
      });
      card.classList.toggle('hidden');
      return;
    }
    if (!e.target.closest('.tl-dot-wrap') && !e.target.closest('.tl-zoom-btn')) {
      document.querySelectorAll('.tl-dot-card:not(.hidden)').forEach(c => c.classList.add('hidden'));
    }
  });

  // Timeline dot double-click → open viewer/popover directly
  document.addEventListener('dblclick', (e) => {
    const dot = e.target.closest('.tl-dot');
    if (!dot) return;
    e.preventDefault();
    const wrap = dot.closest('.tl-dot-wrap');
    if (!wrap) return;
    const card = wrap.querySelector('.tl-dot-card');
    if (!card) return;
    // Ensure card is visible so att-item / popover-item handlers can find it
    card.classList.remove('hidden');
    card.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  });
}

// ── Timeline zoom + auto-scroll setup ────────────────────────

function initTimeline(secEl) {
  const scrollEl = secEl.querySelector('.tl-scroll');
  const innerEl  = secEl.querySelector('.tl-inner');
  if (!scrollEl || !innerEl) return;

  const baseWidth  = parseInt(innerEl.dataset.tlBaseWidth,   10)  || 1600;
  const rangeStart = parseFloat(innerEl.dataset.tlRangeStart)      || 0;
  const totalRange = parseFloat(innerEl.dataset.tlTotalRange)      || 1;
  const centerPct  = parseFloat(scrollEl.dataset.tlCenter)         || 50;
  let   zoom       = 1;

  // ── Adaptive tick ruler ───────────────────────────────────────
  const updateTicks = () => {
    const ruler = secEl.querySelector('.tl-tick-ruler');
    if (!ruler) return;

    const actualWidth = baseWidth * zoom;
    const spanDays    = totalRange / 86400000;
    const pxPerDay    = actualWidth / spanDays;

    // Choose tick interval based on density
    let getNext, format;
    const dt = new Date(rangeStart);
    if (pxPerDay >= 30) {
      dt.setHours(0, 0, 0, 0);
      getNext = d => d.setDate(d.getDate() + 1);
      format  = d => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } else if (pxPerDay >= 6) {
      dt.setHours(0, 0, 0, 0);
      dt.setDate(dt.getDate() - dt.getDay()); // snap to Sunday
      getNext = d => d.setDate(d.getDate() + 7);
      format  = d => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } else if (pxPerDay >= 1.2) {
      dt.setDate(1); dt.setHours(0, 0, 0, 0);
      getNext = d => d.setMonth(d.getMonth() + 1);
      format  = d => d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
    } else if (pxPerDay >= 0.3) {
      dt.setMonth(Math.floor(dt.getMonth() / 3) * 3);
      dt.setDate(1); dt.setHours(0, 0, 0, 0);
      getNext = d => d.setMonth(d.getMonth() + 3);
      format  = d => `Q${Math.floor(d.getMonth() / 3) + 1} '${String(d.getFullYear()).slice(2)}`;
    } else {
      dt.setMonth(0); dt.setDate(1); dt.setHours(0, 0, 0, 0);
      getNext = d => d.setFullYear(d.getFullYear() + 1);
      format  = d => d.getFullYear().toString();
    }

    const rangeEnd = rangeStart + totalRange;
    const parts    = [];
    while (+dt <= rangeEnd + 86400000) {
      const leftPct = Math.max(0.2, Math.min(99.8, ((+dt - rangeStart) / totalRange) * 100));
      parts.push(
        `<div class="absolute flex flex-col items-center" style="left:${leftPct}%; bottom:0; transform:translateX(-50%);">` +
        `<div style="width:1px;height:8px;background:rgba(198,198,208,0.5);"></div>` +
        `<span style="font-size:9px;font-family:monospace;color:rgba(69,70,79,0.5);margin-top:2px;white-space:nowrap;">${format(dt)}</span>` +
        `</div>`
      );
      getNext(dt);
    }
    ruler.innerHTML = parts.join('');
  };

  const applyZoom = (z) => {
    zoom = Math.max(0.2, Math.min(4, z));
    innerEl.style.minWidth = Math.round(baseWidth * zoom) + 'px';
    const target = (centerPct / 100) * baseWidth * zoom - scrollEl.offsetWidth / 2;
    scrollEl.scrollLeft = Math.max(0, target);
    const label = secEl.querySelector('.tl-zoom-label');
    if (label) label.textContent = Math.round(zoom * 100) + '%';
    updateTicks();
  };

  // Default: fit to viewport
  const fitZoom = Math.max(0.2, Math.min(0.7, scrollEl.offsetWidth / baseWidth));
  applyZoom(fitZoom);

  secEl.querySelector('.tl-zoom-in')?.addEventListener('click',
    (e) => { e.stopPropagation(); applyZoom(zoom * 1.5); });
  secEl.querySelector('.tl-zoom-out')?.addEventListener('click',
    (e) => { e.stopPropagation(); applyZoom(zoom / 1.5); });
  secEl.querySelector('.tl-zoom-reset')?.addEventListener('click',
    (e) => { e.stopPropagation(); applyZoom(fitZoom); });
}
