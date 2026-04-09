// ============================================================
// CALENDAR PAGE — month / quarter / year views
// Events (blue) · Deadlines (red) · Emails (green) · Documents (amber)
// ============================================================

import {
  loadProjectEvents,
  loadProjectDeadlines,
  loadProjectAttachments,
  loadProjectEmails,
} from '../api.js';
import { renderProjectSidebar, bindProjectSidebarEvents } from '../components/sidebar_level2.js';
import { renderTopbar }   from '../components/topbar.js';
import { formatDate, skeleton, escHtml } from '../utils.js';
import { initPopovers, registerItems, openPopover } from '../components/popovers.js';

// ── Type config ───────────────────────────────────────────────

const TYPES = {
  event:    { label: 'Event',    icon: 'event',       dot: 'bg-primary',   bg: 'bg-primary/8',  text: 'text-primary',   border: 'border-primary/60',  chip: 'bg-primary/10 text-primary'  },
  deadline: { label: 'Deadline', icon: 'flag',        dot: 'bg-red-500',   bg: 'bg-red-50',     text: 'text-red-600',   border: 'border-red-400',     chip: 'bg-red-50 text-red-600'      },
  email:    { label: 'Email',    icon: 'mail',        dot: 'bg-green-500', bg: 'bg-green-50',   text: 'text-green-700', border: 'border-green-400',   chip: 'bg-green-50 text-green-700'  },
  document: { label: 'Document', icon: 'description', dot: 'bg-amber-500', bg: 'bg-amber-50',   text: 'text-amber-700', border: 'border-amber-400',   chip: 'bg-amber-50 text-amber-700'  },
};

const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

// ── State ─────────────────────────────────────────────────────

const calState = {
  view:        'month',  // 'month' | 'quarter' | 'year'
  year:        new Date().getFullYear(),
  month:       new Date().getMonth(),
  selectedKey: null,
  items:       [],
  itemMap:     new Map(),
};

// ── Entry point ───────────────────────────────────────────────

export async function renderCalendar(params) {
  const projectId = params.id;

  calState.view        = 'month';
  calState.year        = new Date().getFullYear();
  calState.month       = new Date().getMonth();
  calState.selectedKey = null;
  calState.items       = [];
  calState.itemMap     = new Map();

  document.getElementById('app').innerHTML = `
    ${renderProjectSidebar(projectId)}
    <div class="ml-64 min-h-screen bg-surface flex flex-col">
      ${renderTopbar({
        title: 'Calendar',
        breadcrumb: { label: 'Project', href: `#/project/${projectId}` },
      })}
      <div id="cal-body" class="flex-1 flex flex-col px-8 py-6">
        <div class="space-y-4">${skeleton(6)}</div>
      </div>
    </div>`;

  bindProjectSidebarEvents();

  try {
    const [events, deadlines, attachments, emails] = await Promise.all([
      loadProjectEvents(projectId).catch(() => []),
      loadProjectDeadlines(projectId).catch(() => []),
      loadProjectAttachments(projectId).catch(() => []),
      loadProjectEmails(projectId).catch(() => []),
    ]);

    calState.items = normalize(events, deadlines, attachments, emails);
    buildItemMap();

    // Register popover-capable types
    initPopovers();
    registerItems('event',    events,    'event_id');
    registerItems('deadline', deadlines, 'deadline_id');

    renderCalBody();
  } catch (err) {
    document.getElementById('cal-body').innerHTML =
      `<p class="text-error text-sm">${err.message}</p>`;
  }
}

// ── Normalize & index ─────────────────────────────────────────

function normalize(events, deadlines, attachments, emails) {
  return [
    ...events.map(e => ({
      type: 'event', date: parseDate(e.event_start_date), endDate: parseDate(e.event_end_date),
      title: e.event_name ?? e.description ?? 'Event', id: e.event_id, raw: e,
    })),
    ...deadlines.map(d => ({
      type: 'deadline', date: parseDate(d.deadline_date),
      title: d.title ?? d.description ?? 'Deadline', id: d.deadline_id, raw: d,
    })),
    ...emails.map(e => ({
      type: 'email', date: parseDate(e.date),
      title: e.subject ?? 'Email', id: e.email_id ?? e.message_id, raw: e,
    })),
    ...attachments.map(a => ({
      type: 'document', date: parseDate(a.file_date ?? a.created_at),
      title: a.filename ?? 'Document', id: a.file_id, raw: a,
    })),
  ].filter(item => item.date !== null);
}

function buildItemMap() {
  calState.itemMap = new Map();
  calState.items.forEach(item => {
    addToMap(toKey(item.date), item, false);
    if (item.endDate && item.type === 'event') {
      const cur = new Date(item.date);
      cur.setDate(cur.getDate() + 1);
      while (cur <= item.endDate) {
        addToMap(toKey(cur), { ...item, spanOnly: true }, true);
        cur.setDate(cur.getDate() + 1);
      }
    }
  });
}

function addToMap(key, item, spanOnly) {
  if (!calState.itemMap.has(key)) calState.itemMap.set(key, []);
  if (!calState.itemMap.get(key).some(x => x.id === item.id))
    calState.itemMap.get(key).push(spanOnly ? { ...item, spanOnly: true } : item);
}

// ── Page shell ────────────────────────────────────────────────

function renderCalBody() {
  document.getElementById('cal-body').innerHTML = `

    <!-- Toolbar -->
    <div class="flex items-center justify-between mb-5 flex-wrap gap-3">

      <!-- Nav -->
      <div class="flex items-center gap-2">
        <button id="cal-prev"
          class="w-8 h-8 flex items-center justify-center rounded-lg bg-surface-container hover:bg-surface-container-high transition-colors text-on-surface-variant">
          <span class="material-symbols-outlined text-[18px]">chevron_left</span>
        </button>
        <h2 id="cal-title" class="font-headline font-bold text-lg text-primary min-w-[180px] text-center"></h2>
        <button id="cal-next"
          class="w-8 h-8 flex items-center justify-center rounded-lg bg-surface-container hover:bg-surface-container-high transition-colors text-on-surface-variant">
          <span class="material-symbols-outlined text-[18px]">chevron_right</span>
        </button>
        <button id="cal-today"
          class="ml-1 px-3 h-8 text-xs font-bold text-secondary ring-1 ring-secondary/20 rounded-lg hover:bg-secondary/5 transition-colors">
          Today
        </button>
      </div>

      <div class="flex items-center gap-4">
        <!-- Legend -->
        <div class="flex items-center gap-4 flex-wrap">
          ${Object.entries(TYPES).map(([, cfg]) => `
            <div class="flex items-center gap-1.5">
              <span class="w-2 h-2 rounded-full ${cfg.dot} flex-shrink-0"></span>
              <span class="text-[11px] font-semibold text-on-surface-variant">${cfg.label}</span>
            </div>`).join('')}
        </div>
        <!-- View switcher -->
        <div class="flex rounded-lg overflow-hidden ring-1 ring-outline-variant/20 flex-shrink-0">
          ${['month','quarter','year'].map(v => `
            <button data-view="${v}" id="view-btn-${v}"
              class="view-btn px-3 py-1.5 text-xs font-bold capitalize transition-colors
                     ${calState.view === v
                       ? 'bg-primary-container text-on-primary'
                       : 'bg-surface-container text-on-surface-variant hover:bg-surface-container-high'}">
              ${v}
            </button>`).join('')}
        </div>
      </div>

    </div>

    <!-- Content area (injected by renderCurrentView) -->
    <div id="cal-content" class="flex-1 flex gap-5 min-h-0"></div>`;

  bindToolbarEvents();
  renderCurrentView();
}

function renderCurrentView() {
  // Update title
  const title = document.getElementById('cal-title');
  if (calState.view === 'month') {
    title.textContent = new Date(calState.year, calState.month, 1)
      .toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  } else if (calState.view === 'quarter') {
    const q = Math.floor(calState.month / 3) + 1;
    title.textContent = `Q${q} ${calState.year}`;
  } else {
    title.textContent = `${calState.year}`;
  }

  // Update view button styles
  document.querySelectorAll('.view-btn').forEach(btn => {
    const active = btn.dataset.view === calState.view;
    btn.classList.toggle('bg-primary-container', active);
    btn.classList.toggle('text-on-primary', active);
    btn.classList.toggle('bg-surface-container', !active);
    btn.classList.toggle('text-on-surface-variant', !active);
  });

  const content = document.getElementById('cal-content');
  if (calState.view === 'month')   renderMonthView(content);
  else if (calState.view === 'quarter') renderQuarterView(content);
  else renderYearView(content);
}

// ── Month view ────────────────────────────────────────────────

function renderMonthView(container) {
  container.innerHTML = `
    <div class="flex-1 min-w-0 flex flex-col">
      ${weekdayHeader('text-[10px]')}
      <div id="cal-grid" class="grid grid-cols-7 border border-outline-variant/10 rounded-xl overflow-hidden flex-1"></div>
    </div>
    ${detailPanelHTML()}`;

  fillMonthGrid('cal-grid', calState.year, calState.month, { chipsMax: 2, cellMinH: 'min-h-[84px]' });
  bindDetailPanel();
  if (calState.selectedKey) selectDay(calState.selectedKey);
}

function fillMonthGrid(gridId, year, month, { chipsMax = 2, cellMinH = 'min-h-[84px]', compact = false } = {}) {
  const grid       = document.getElementById(gridId);
  if (!grid) return;
  const todayKey   = toKey(new Date());
  const offset     = (new Date(year, month, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const prevDays   = new Date(year, month, 0).getDate();
  const total      = Math.ceil((offset + daysInMonth) / 7) * 7;

  let html = '';
  for (let i = 0; i < total; i++) {
    let d, current;
    if (i < offset)                    { d = new Date(year, month - 1, prevDays - offset + i + 1); current = false; }
    else if (i < offset + daysInMonth) { d = new Date(year, month, i - offset + 1);                 current = true;  }
    else                               { d = new Date(year, month + 1, i - offset - daysInMonth + 1); current = false; }

    const key        = toKey(d);
    const isToday    = key === todayKey;
    const isSelected = key === calState.selectedKey;
    const isWeekend  = d.getDay() === 0 || d.getDay() === 6;
    const all        = calState.itemMap.get(key) ?? [];
    const real       = all.filter(x => !x.spanOnly);
    const typeSet    = [...new Set(real.map(x => x.type))];
    const hasSpan    = all.some(x => x.spanOnly && x.type === 'event');
    const vis        = real.slice(0, chipsMax);
    const more       = real.length - vis.length;

    const chips = compact ? '' : vis.map(item => {
      const c = TYPES[item.type];
      return `<div class="text-[9px] font-semibold truncate rounded px-1 py-px ${c.chip} leading-tight">${escHtml(item.title)}</div>`;
    }).join('') + (more > 0 ? `<div class="text-[9px] text-on-surface-variant/50 px-0.5">+${more}</div>` : '');

    const dots = typeSet.map(t => `<span class="w-1.5 h-1.5 rounded-full ${TYPES[t].dot} flex-shrink-0"></span>`).join('');

    html += `
      <div class="cal-cell relative bg-surface ${cellMinH} ${compact ? 'min-h-[52px]' : ''} p-1.5 flex flex-col cursor-pointer
                  transition-colors border-b border-r border-outline-variant/10
                  ${!current ? 'opacity-30 pointer-events-none' : ''}
                  ${isWeekend && current ? 'bg-surface-container/40' : ''}
                  ${isToday ? 'ring-2 ring-inset ring-secondary/60' : ''}
                  ${isSelected && current ? '!bg-secondary/8' : current ? 'hover:bg-surface-container/50' : ''}"
           data-key="${key}">
        ${hasSpan ? `<div class="absolute top-0 left-0 right-0 h-0.5 bg-primary/25"></div>` : ''}
        <div class="flex items-start justify-between mb-0.5">
          <span class="${isToday
            ? 'w-5 h-5 rounded-full bg-secondary text-on-primary flex items-center justify-center text-[10px] font-black'
            : 'text-xs font-semibold text-on-surface'}">${d.getDate()}</span>
          <div class="flex items-center gap-px">${dots}</div>
        </div>
        <div class="space-y-px flex-1 overflow-hidden">${chips}</div>
      </div>`;
  }

  grid.innerHTML = html;
  grid.querySelectorAll('.cal-cell').forEach(cell =>
    cell.addEventListener('click', () => selectDay(cell.dataset.key))
  );
}

// ── Quarter view ──────────────────────────────────────────────

function renderQuarterView(container) {
  const q0 = Math.floor(calState.month / 3) * 3; // first month of current quarter

  container.innerHTML = `
    <div class="flex-1 min-w-0 flex gap-3 min-h-0">
      ${[0,1,2].map(i => {
        const m = q0 + i;
        const y = calState.year + Math.floor(m / 12);
        const monthIdx = ((m % 12) + 12) % 12;
        const name = new Date(y, monthIdx, 1).toLocaleDateString('en-US', { month: 'long' });
        return `
          <div class="flex-1 min-w-0 flex flex-col">
            <p class="font-headline font-bold text-sm text-primary mb-2 px-0.5">${name}</p>
            ${weekdayHeader('text-[9px]')}
            <div id="qgrid-${i}" class="grid grid-cols-7 border border-outline-variant/10 rounded-xl overflow-hidden flex-1"></div>
          </div>`;
      }).join('')}
    </div>
    ${detailPanelHTML()}`;

  [0,1,2].forEach(i => {
    const m = q0 + i;
    const y = calState.year + Math.floor(m / 12);
    fillMonthGrid(`qgrid-${i}`, y, ((m % 12) + 12) % 12, { chipsMax: 1, cellMinH: 'min-h-[60px]' });
  });

  bindDetailPanel();
  if (calState.selectedKey) selectDay(calState.selectedKey);
}

// ── Year view ─────────────────────────────────────────────────

function renderYearView(container) {
  const months = Array.from({ length: 12 }, (_, i) => i);

  // Count items per month for summary badges
  const monthCounts = months.map(m => {
    let count = 0;
    calState.items.forEach(item => {
      if (item.date.getFullYear() === calState.year && item.date.getMonth() === m) count++;
    });
    return count;
  });

  container.innerHTML = `
    <div class="flex-1 min-w-0 grid grid-cols-4 gap-4">
      ${months.map(m => {
        const name   = MONTHS_SHORT[m];
        const count  = monthCounts[m];
        const isNow  = m === new Date().getMonth() && calState.year === new Date().getFullYear();
        return `
          <div class="bg-surface-container-lowest rounded-xl border border-outline-variant/10 p-3 flex flex-col gap-1
                      hover:border-secondary/30 hover:shadow-sm transition-all cursor-pointer year-month-card
                      ${isNow ? 'ring-2 ring-secondary/40' : ''}"
               data-month="${m}">
            <div class="flex items-center justify-between mb-1">
              <span class="font-headline font-bold text-sm ${isNow ? 'text-secondary' : 'text-primary'}">${name}</span>
              ${count > 0 ? `<span class="text-[9px] font-bold text-on-surface-variant/50">${count} item${count !== 1 ? 's' : ''}</span>` : ''}
            </div>
            ${weekdayHeaderMini()}
            ${buildMiniMonthGrid(calState.year, m)}
          </div>`;
      }).join('')}
    </div>`;

  // Click a month → zoom into month view
  container.querySelectorAll('.year-month-card').forEach(card => {
    card.addEventListener('click', () => {
      calState.month = Number(card.dataset.month);
      calState.view  = 'month';
      renderCurrentView();
    });
  });
}

function buildMiniMonthGrid(year, month) {
  const offset      = (new Date(year, month, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const prevDays    = new Date(year, month, 0).getDate();
  const total       = Math.ceil((offset + daysInMonth) / 7) * 7;
  const todayKey    = toKey(new Date());

  let cells = '';
  for (let i = 0; i < total; i++) {
    let d, current;
    if (i < offset)                    { d = new Date(year, month - 1, prevDays - offset + i + 1); current = false; }
    else if (i < offset + daysInMonth) { d = new Date(year, month, i - offset + 1);                 current = true;  }
    else                               { d = new Date(year, month + 1, i - offset - daysInMonth + 1); current = false; }

    const key     = toKey(d);
    const isToday = key === todayKey;
    const items   = current ? (calState.itemMap.get(key) ?? []).filter(x => !x.spanOnly) : [];
    const types   = [...new Set(items.map(x => x.type))];

    cells += `
      <div class="flex flex-col items-center py-0.5 ${!current ? 'opacity-20' : ''}">
        <span class="text-[9px] ${isToday
          ? 'w-4 h-4 rounded-full bg-secondary text-on-primary flex items-center justify-center font-black'
          : 'text-on-surface-variant/60 font-medium'}">${d.getDate()}</span>
        <div class="flex gap-px mt-px flex-wrap justify-center">
          ${types.slice(0, 3).map(t => `<span class="w-1 h-1 rounded-full ${TYPES[t].dot}"></span>`).join('')}
        </div>
      </div>`;
  }

  return `<div class="grid grid-cols-7">${cells}</div>`;
}

// ── Detail panel ──────────────────────────────────────────────

function detailPanelHTML() {
  return `
    <div class="w-72 flex-shrink-0 bg-surface-container-low rounded-xl border border-outline-variant/10 flex flex-col overflow-hidden self-start sticky top-6">
      <div class="px-5 py-4 border-b border-outline-variant/10">
        <p id="cal-detail-date" class="font-headline font-bold text-sm text-primary">Select a day</p>
        <p id="cal-detail-count" class="text-[11px] text-on-surface-variant mt-0.5"></p>
      </div>
      <div id="cal-detail-list" class="overflow-y-auto p-4 space-y-2 max-h-[calc(100vh-280px)]">
        <p class="text-xs text-on-surface-variant/40 text-center py-10">Click a day to see items</p>
      </div>
    </div>`;
}

function bindDetailPanel() {
  // Close button is not present in this version — panel is persistent
}

function selectDay(key) {
  calState.selectedKey = key;

  document.querySelectorAll('.cal-cell').forEach(el =>
    el.classList.toggle('!bg-secondary/8', el.dataset.key === key)
  );

  const [y, m, d]  = key.split('-').map(Number);
  const date        = new Date(y, m - 1, d);
  const items       = (calState.itemMap.get(key) ?? []).filter(x => !x.spanOnly);

  const dateEl  = document.getElementById('cal-detail-date');
  const countEl = document.getElementById('cal-detail-count');
  const listEl  = document.getElementById('cal-detail-list');
  if (!dateEl) return;

  dateEl.textContent  = date.toLocaleDateString('en-US', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  countEl.textContent = items.length ? `${items.length} item${items.length !== 1 ? 's' : ''}` : 'Nothing scheduled';

  if (!items.length) {
    listEl.innerHTML = `<p class="text-xs text-on-surface-variant/40 text-center py-10">No items on this day</p>`;
    return;
  }

  const order = { deadline: 0, event: 1, email: 2, document: 3 };
  const sorted = [...items].sort((a, b) => (order[a.type] ?? 9) - (order[b.type] ?? 9));

  const POPOVER_TYPES = new Set(['event', 'deadline']);

  listEl.innerHTML = sorted.map(item => {
    const cfg       = TYPES[item.type];
    const meta      = itemMeta(item);
    const hasPopover = POPOVER_TYPES.has(item.type);
    const popAttrs  = hasPopover
      ? `data-popover-type="${item.type}" data-popover-id="${escHtml(item.id)}"`
      : '';
    const cursor    = hasPopover ? 'cursor-pointer hover:brightness-95' : '';
    return `
      <div class="rounded-xl p-3 ${cfg.bg} border-l-[3px] ${cfg.border} transition-all ${cursor} ${hasPopover ? 'popover-item' : ''}" ${popAttrs}>
        <div class="flex items-start gap-2">
          <span class="material-symbols-outlined text-[14px] ${cfg.text} mt-0.5 flex-shrink-0">${cfg.icon}</span>
          <div class="min-w-0 flex-1">
            <p class="text-xs font-bold ${cfg.text} leading-tight break-words">${escHtml(item.title)}</p>
            ${meta ? `<p class="text-[10px] text-on-surface-variant mt-1 leading-snug">${meta}</p>` : ''}
            ${hasPopover ? `<p class="text-[9px] text-on-surface-variant/40 mt-1.5 font-semibold uppercase tracking-wide">Click to view details</p>` : ''}
          </div>
        </div>
      </div>`;
  }).join('');
}

function itemMeta(item) {
  switch (item.type) {
    case 'event':
      return [
        item.raw.category     ? escHtml(item.raw.category)      : null,
        item.raw.significance ? `Sig: ${escHtml(item.raw.significance)}` : null,
        item.endDate          ? `Until ${formatDate(item.endDate)}` : null,
        item.raw.description  ? escHtml(item.raw.description)   : null,
      ].filter(Boolean).join(' · ');
    case 'deadline':
      return [
        item.raw.party_role  ? escHtml(item.raw.party_role)  : null,
        item.raw.description ? escHtml(item.raw.description) : null,
      ].filter(Boolean).join(' · ');
    case 'email':
      return item.raw.from_addr ? `From: ${escHtml(item.raw.from_addr)}` : null;
    case 'document':
      return item.raw.file_type ? escHtml(item.raw.file_type) : null;
    default:
      return null;
  }
}

// ── Toolbar events ────────────────────────────────────────────

function bindToolbarEvents() {
  document.getElementById('cal-prev')?.addEventListener('click', () => {
    if      (calState.view === 'month')   { calState.month--; if (calState.month < 0)  { calState.month = 11; calState.year--; } }
    else if (calState.view === 'quarter') { calState.month -= 3; if (calState.month < 0) { calState.month += 12; calState.year--; } }
    else                                  { calState.year--; }
    renderCurrentView();
  });

  document.getElementById('cal-next')?.addEventListener('click', () => {
    if      (calState.view === 'month')   { calState.month++; if (calState.month > 11) { calState.month = 0;  calState.year++; } }
    else if (calState.view === 'quarter') { calState.month += 3; if (calState.month > 11) { calState.month -= 12; calState.year++; } }
    else                                  { calState.year++; }
    renderCurrentView();
  });

  document.getElementById('cal-today')?.addEventListener('click', () => {
    calState.year  = new Date().getFullYear();
    calState.month = new Date().getMonth();
    renderCurrentView();
  });

  document.querySelectorAll('.view-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      calState.view = btn.dataset.view;
      renderCurrentView();
    });
  });
}

// ── Shared helpers ────────────────────────────────────────────

function weekdayHeader(textClass) {
  return `
    <div class="grid grid-cols-7 mb-1">
      ${['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d =>
        `<div class="text-center ${textClass} font-bold uppercase tracking-wider text-on-surface-variant/40 pb-1.5">${d}</div>`
      ).join('')}
    </div>`;
}

function weekdayHeaderMini() {
  return `
    <div class="grid grid-cols-7 mb-0.5">
      ${['M','T','W','T','F','S','S'].map(d =>
        `<div class="text-center text-[8px] font-bold text-on-surface-variant/25">${d}</div>`
      ).join('')}
    </div>`;
}

function parseDate(str) {
  if (!str) return null;
  const d = new Date(str);
  return isNaN(d.getTime()) ? null : d;
}

function toKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
