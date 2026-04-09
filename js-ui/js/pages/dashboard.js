// ============================================================
// COMPANY DASHBOARD — main landing page (Level 1)
// Layout ref: new-ui/mainpage/mainpage_dashboard.html
// ============================================================

import { loadProjects }                                  from '../api.js';
import { renderMainSidebar, bindMainSidebarEvents }      from '../components/sidebar.js';
import { renderTopbar }                                  from '../components/topbar.js';
import { appState }                                      from '../state.js';
import { formatDate, skeleton }                          from '../utils.js';

export async function renderDashboard() {
  document.getElementById('app').innerHTML = `
    ${renderMainSidebar()}
    <div class="ml-64 min-h-screen bg-surface">
      ${renderTopbar({ title: 'Dashboard' })}
      <div id="dashboard-content" class="px-10 py-8">
        <div class="space-y-4">${skeleton(6)}</div>
      </div>
    </div>`;

  bindMainSidebarEvents();

  try {
    const projects = await loadProjects(appState.user.id);
    document.getElementById('dashboard-content').innerHTML = buildDashboardHTML(projects ?? []);
    bindDashboardEvents(projects ?? []);
  } catch (err) {
    document.getElementById('dashboard-content').innerHTML =
      `<p class="text-error text-sm font-body">${err.message}</p>`;
  }
}

// ── Build ─────────────────────────────────────────────────────

function buildDashboardHTML(projects) {
  const active = projects.filter(p => p.status !== 'closed').length;
  const closed = projects.filter(p => p.status === 'closed').length;

  return `
    <!-- Page header -->
    <div class="mb-10">
      <h2 class="font-headline font-bold text-3xl text-primary-container tracking-tight mb-1">Company Overview</h2>
      <p class="text-on-surface-variant text-sm max-w-2xl">
        Visualizing the intersection of legal strategy and firm growth. Data reflects active quarter performance indicators.
      </p>
    </div>

    <!-- Metric cards -->
    <div class="grid grid-cols-2 xl:grid-cols-4 gap-5 mb-12">
      ${metricCard('folder_special', 'bg-primary-fixed', 'text-primary-container', projects.length, 'Projects', '+12%', 'text-green-600 bg-green-50')}
      ${metricCard('forum', 'bg-secondary-fixed', 'text-secondary', '2k+', 'Conversations', 'Live', 'text-blue-600 bg-blue-50')}
      ${metricCard('description', 'bg-surface-container', 'text-on-surface', '1,250', 'Documents', 'Audit Ready', 'text-slate-400 bg-slate-50')}
      ${metricCard('mail', 'bg-tertiary-fixed', 'text-on-tertiary-container', '300', 'Emails', 'Priority', 'text-orange-600 bg-orange-50')}
    </div>

    <!-- Portfolio Timeline -->
    ${buildTimeline(projects)}

    <!-- Bottom grid -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">

      <!-- Team Productivity -->
      <div class="lg:col-span-2 bg-surface-container-lowest rounded-xl overflow-hidden">
        <div class="px-8 py-6 flex justify-between items-center border-b border-outline-variant/5">
          <h3 class="font-headline font-bold text-lg text-primary">Team Productivity</h3>
          <div class="flex gap-5">
            <span class="flex items-center gap-2 text-xs font-semibold text-on-surface-variant">
              <span class="w-3 h-3 rounded-full bg-primary-container"></span>Active Projects
            </span>
            <span class="flex items-center gap-2 text-xs font-semibold text-on-surface-variant">
              <span class="w-3 h-3 rounded-full bg-secondary-container"></span>Reviews
            </span>
          </div>
        </div>
        <div class="p-8">
          <div class="flex items-end gap-4 h-48 w-full">
            ${barDay('MON', 60, 20)}
            ${barDay('TUE', 85, 10)}
            ${barDay('WED', 45, 35)}
            ${barDay('THU', 75, 15)}
            ${barDay('FRI', 95,  5)}
            ${barDay('SAT', 20,  0, true)}
          </div>
        </div>
      </div>

      <!-- Critical Actions -->
      <div class="bg-surface-container-lowest rounded-xl p-6">
        <h3 class="font-headline font-bold text-lg text-primary mb-6">Critical Actions</h3>
        <div class="space-y-6">
          <div class="flex gap-4">
            <div class="w-2 h-2 rounded-full bg-tertiary-fixed-dim mt-1.5 shrink-0"></div>
            <div>
              <p class="text-sm font-semibold text-primary">Document Signature Required</p>
              <p class="text-[11px] text-on-surface-variant mb-2">${projects[0]?.title ?? 'Latest Project'}</p>
              <span class="text-[10px] bg-surface-container text-on-surface-variant px-2 py-0.5 rounded-full font-bold">URGENT</span>
            </div>
          </div>
          <div class="flex gap-4">
            <div class="w-2 h-2 rounded-full bg-secondary mt-1.5 shrink-0"></div>
            <div>
              <p class="text-sm font-semibold text-primary">New Case File Uploaded</p>
              <p class="text-[11px] text-on-surface-variant">${projects[1]?.title ?? 'Active Case'}</p>
            </div>
          </div>
          <div class="flex gap-4">
            <div class="w-2 h-2 rounded-full bg-green-500 mt-1.5 shrink-0"></div>
            <div>
              <p class="text-sm font-semibold text-primary">Timeline Marker Reached</p>
              <p class="text-[11px] text-on-surface-variant">${projects[2]?.title ?? 'Ongoing Matter'}</p>
            </div>
          </div>
        </div>
        <button class="w-full mt-8 py-3 text-xs font-bold text-secondary ring-1 ring-secondary/20 rounded-lg hover:bg-secondary/5 transition-colors">
          VIEW FULL ACTIVITY LOG
        </button>
      </div>

    </div>`;
}

// ── Helpers ───────────────────────────────────────────────────

function metricCard(icon, bgClass, iconClass, value, label, badge, badgeClass) {
  return `
    <div class="bg-surface-container-lowest rounded-xl p-6 flex flex-col justify-between">
      <div class="flex justify-between items-start">
        <div class="w-10 h-10 ${bgClass} flex items-center justify-center rounded-lg">
          <span class="material-symbols-outlined ${iconClass}">${icon}</span>
        </div>
        <span class="text-xs font-bold px-2 py-1 rounded ${badgeClass}">${badge}</span>
      </div>
      <div class="mt-6">
        <p class="font-headline font-bold text-3xl text-primary">${value}</p>
        <p class="text-on-surface-variant font-medium text-xs uppercase tracking-wider mt-1">${label}</p>
      </div>
    </div>`;
}

function barDay(label, activeH, reviewH, muted = false) {
  const wrapClass = muted ? 'flex-1 bg-slate-50 rounded-t-lg relative opacity-40' : 'flex-1 bg-slate-50 rounded-t-lg relative group';
  const barColor  = muted ? 'bg-surface-container' : 'bg-primary-container';
  return `
    <div class="${wrapClass}">
      <div class="absolute bottom-0 w-full ${barColor} rounded-t-lg" style="height:${activeH}%"></div>
      ${reviewH ? `<div class="absolute w-full bg-secondary-container rounded-t-sm" style="bottom:${activeH}%;height:${reviewH}%"></div>` : ''}
      <span class="absolute -bottom-6 left-1/2 -translate-x-1/2 text-[10px] font-bold text-on-surface-variant">${label}</span>
    </div>`;
}

function buildTimeline(projects) {
  if (!projects.length) return '';

  const markers = projects.slice(0, 5).map((p, i) => {
    const isToday   = i === 2; // center marker = "today"
    const dotClass  = isToday
      ? 'w-4 h-4 bg-primary-container ring-4 ring-secondary-container relative z-10 rounded-full transition-transform group-hover:scale-125'
      : 'w-3.5 h-3.5 bg-secondary ring-4 ring-secondary-container/40 relative z-10 rounded-full transition-transform group-hover:scale-125';
    const date = formatDate(p.created_at, { day: 'numeric', month: 'short', year: '2-digit' });

    return `
      <div class="relative group cursor-pointer" data-project="${p.project_id}">
        <div class="absolute -top-16 left-1/2 -translate-x-1/2 w-48 text-center opacity-0 group-hover:opacity-100 transition-opacity bg-white/90 backdrop-blur-md p-3 rounded-lg shadow-2xl z-20 pointer-events-none">
          <p class="text-[10px] uppercase font-bold text-secondary mb-1">${date}</p>
          <p class="text-xs font-semibold leading-tight">${p.title}</p>
        </div>
        <div class="${dotClass}"></div>
        <div class="absolute top-8 left-1/2 -translate-x-1/2 text-center w-32">
          <p class="text-sm font-bold text-primary truncate">${p.title}</p>
          <p class="text-[11px] text-on-surface-variant font-medium mt-0.5">${date}</p>
        </div>
      </div>`;
  });

  return `
    <div class="bg-surface-container rounded-xl p-8 mb-12">
      <div class="flex justify-between items-end mb-12">
        <div>
          <h3 class="font-headline font-bold text-xl text-primary mb-1">Portfolio Timeline</h3>
          <p class="text-on-surface-variant text-sm">Quarterly roadmap of major active litigation and advisory.</p>
        </div>
        <button class="flex items-center gap-2 bg-primary-container text-on-primary px-4 py-2 rounded-lg text-sm font-semibold hover:opacity-90 transition-opacity">
          <span class="material-symbols-outlined text-sm">filter_list</span>Filter Timeline
        </button>
      </div>
      <div class="relative pt-12 pb-16 px-4">
        <div class="absolute top-1/2 left-0 w-full h-[2px] bg-secondary/20 -translate-y-1/2"></div>
        <!-- Today marker -->
        <div class="absolute top-1/2 left-[50%] -translate-y-1/2 h-20 w-[2px] bg-tertiary-fixed-dim z-0 flex flex-col items-center pointer-events-none">
          <span class="bg-tertiary-fixed-dim text-[9px] font-black text-on-tertiary-fixed px-2 py-0.5 rounded-sm -mt-5 whitespace-nowrap">TODAY</span>
        </div>
        <div class="relative flex justify-between">
          ${markers.join('')}
        </div>
      </div>
    </div>`;
}

// ── Events ────────────────────────────────────────────────────

function bindDashboardEvents(projects) {
  document.querySelectorAll('[data-project]').forEach(el => {
    el.addEventListener('click', () => {
      window.location.hash = `/project/${el.dataset.project}`;
    });
  });
}
