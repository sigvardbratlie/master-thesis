// ============================================================
// PORTFOLIO PAGE — projects overview (main page)
// Mirrors: ui/src/ui/ui_components/project_component.py
// ============================================================

import { loadProjects, createProject, deleteProject } from '../api.js';
import { renderSidebar, bindSidebarEvents }            from '../components/sidebar.js';
import { renderTopbar }                                from '../components/topbar.js';
import { appState }                                    from '../state.js';
import { formatDate, timeAgo, toast, skeleton, uuid }  from '../utils.js';
import { logger }                                      from '../logger.js';

const log = logger.child({ module: 'portfolio' });

export async function renderPortfolio() {
  const shell = `
    ${renderSidebar()}
    <div class="ml-64 min-h-screen bg-surface">
      ${renderTopbar({ title: 'Projects' })}
      <div id="portfolio-content" class="px-10 py-8">
        <div class="space-y-4">${skeleton(4)}</div>
      </div>
    </div>
    ${renderNewProjectModal()}`;

  document.getElementById('app').innerHTML = shell;
  bindSidebarEvents();
  bindPortfolioEvents();

  await loadPortfolioContent();
}

async function loadPortfolioContent() {
  const container = document.getElementById('portfolio-content');

  // Debug: sjekk at appState er satt
  log.info({ userId: appState.user?.id, userEmail: appState.user?.email }, 'loadPortfolioContent start');

  if (!appState.user?.id) {
    log.error({}, 'appState.user.id er null — bruker ikke logget inn?');
    container.innerHTML = `<p class="text-error text-sm">Bruker ikke funnet i appState. Sjekk Console.</p>`;
    return;
  }

  try {
    log.debug({ userId: appState.user.id }, 'Henter prosjekter fra Supabase...');
    const projects = await loadProjects(appState.user.id);
    log.info({ count: projects?.length }, 'Prosjekter hentet');

    if (!projects?.length) {
      log.warn({}, 'Ingen prosjekter returnert — sjekk RLS-regler i Supabase');
    }

    container.innerHTML = buildPortfolioHTML(projects);
    bindProjectCards(projects);
  } catch (err) {
    log.error({ err: err.message }, 'loadPortfolioContent feilet');
    container.innerHTML = `<p class="text-error text-sm font-body p-4">Feil: ${err.message}</p>`;
  }
}

function buildPortfolioHTML(projects) {
  if (!projects?.length) return renderEmptyState();

  // Upcoming deadlines timeline (from projects with deadlines — simplified)
  const timelineHtml = buildTimeline(projects);
  const gridHtml     = buildProjectGrid(projects);

  return `
    <!-- Stats row -->
    <div class="grid grid-cols-4 gap-5 mb-10">
      ${statCard('folder_open',    'Active Cases',   projects.length,                   'text-secondary')}
      ${statCard('event_upcoming', 'Upcoming',       projects.filter(p => p.status !== 'closed').length, 'text-tertiary-fixed-dim')}
      ${statCard('check_circle',   'Closed',         projects.filter(p => p.status === 'closed').length, 'text-green-600')}
      ${statCard('schedule',       'Last Updated',   timeAgo(projects[0]?.created_at),  'text-on-surface-variant')}
    </div>

    <!-- Timeline -->
    ${timelineHtml}

    <!-- Grid header -->
    <div class="flex items-center justify-between mb-6 mt-12">
      <h2 class="font-headline font-bold text-2xl text-primary">Active Projects</h2>
      <div class="flex items-center gap-3">
        <button id="btn-filter" class="flex items-center gap-1.5 text-sm text-on-surface-variant hover:text-primary font-medium transition-colors">
          <span class="material-symbols-outlined text-[18px]">filter_list</span>Filter
        </button>
        <button id="btn-sort" class="flex items-center gap-1.5 text-sm text-on-surface-variant hover:text-primary font-medium transition-colors">
          <span class="material-symbols-outlined text-[18px]">sort</span>Sort
        </button>
      </div>
    </div>

    <!-- Project cards grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
      ${gridHtml}
    </div>`;
}

function statCard(icon, label, value, colorClass) {
  return `
    <div class="bg-surface-container-lowest rounded-xl p-5 ring-1 ring-outline-variant/10">
      <div class="flex items-center gap-3 mb-3">
        <span class="material-symbols-outlined text-[20px] ${colorClass}">${icon}</span>
        <span class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">${label}</span>
      </div>
      <p class="font-headline font-black text-2xl text-primary">${value}</p>
    </div>`;
}

function buildTimeline(projects) {
  if (projects.length < 2) return '';

  const items = projects.slice(0, 5).map((p, i) => {
    const isCenter  = i === Math.floor(Math.min(projects.length, 5) / 2);
    const isAbove   = i % 2 === 0;
    const dotClass  = isCenter
      ? 'w-5 h-5 bg-primary ring-[5px] ring-secondary-container/30 animate-pulse'
      : 'w-3.5 h-3.5 bg-secondary ring-4 ring-surface';
    const cardClass = isCenter
      ? 'bg-surface-container-lowest ring-1 ring-secondary/20 shadow-lg scale-105 p-5'
      : 'bg-surface-container-low ring-1 ring-outline-variant/10 shadow-sm p-4 opacity-80 hover:opacity-100 transition-opacity';

    const card = `
      <div class="${cardClass} rounded-xl w-44 transition-all">
        <span class="text-[9px] font-black uppercase text-secondary block mb-1">${formatDate(p.created_at, { day: 'numeric', month: 'short' })}</span>
        <p class="${isCenter ? 'text-sm font-bold' : 'text-xs font-semibold'} text-primary leading-tight line-clamp-2">${p.title}</p>
      </div>`;

    return isAbove
      ? `<div class="relative flex flex-col items-center group cursor-pointer" data-project="${p.project_id}">
           ${card}
           <div class="${dotClass} rounded-full mt-3 z-10 flex-shrink-0"></div>
         </div>`
      : `<div class="relative flex flex-col items-center group cursor-pointer" data-project="${p.project_id}">
           <div class="${dotClass} rounded-full mb-3 z-10 flex-shrink-0"></div>
           ${card}
         </div>`;
  });

  return `
    <section class="mb-4">
      <div class="flex items-end justify-between mb-5">
        <div>
          <h2 class="font-headline font-extrabold text-2xl text-primary tracking-tight">Portfolio Timeline</h2>
          <p class="text-on-surface-variant text-sm font-body mt-1">Active trajectory across ongoing engagements</p>
        </div>
      </div>
      <div class="relative bg-surface-container-low rounded-2xl px-8 py-8 overflow-hidden">
        <div class="absolute left-8 right-8 top-1/2 h-[2px] bg-secondary/20 -translate-y-1/2 pointer-events-none"></div>
        <div class="relative flex justify-around items-center">
          ${items.join('')}
        </div>
      </div>
    </section>`;
}

function buildProjectGrid(projects) {
  return projects.map(p => projectCard(p)).join('');
}

function projectCard(p) {
  const statusBadge = p.status === 'closed'
    ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-surface-container text-on-surface-variant">Closed</span>`
    : `<span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-secondary-container/30 text-on-secondary-container">Active</span>`;

  return `
    <div class="group bg-surface-container-lowest hover:bg-white rounded-xl p-6 ring-1 ring-outline-variant/10
                hover:shadow-[0_20px_40px_-15px_rgba(0,0,0,0.07)] transition-all cursor-pointer project-card"
         data-project-id="${p.project_id}">

      <!-- Header row -->
      <div class="flex justify-between items-start mb-5">
        <div class="flex gap-2 flex-wrap">
          ${statusBadge}
        </div>
        <button class="p-1 rounded hover:bg-surface-container transition-colors project-menu-btn"
                data-project-id="${p.project_id}" data-title="${p.title}">
          <span class="material-symbols-outlined text-[18px] text-on-surface-variant/40 hover:text-on-surface-variant">more_horiz</span>
        </button>
      </div>

      <!-- Title -->
      <h3 class="font-headline font-extrabold text-lg text-primary mb-1 group-hover:text-secondary transition-colors leading-tight line-clamp-2">
        ${p.title}
      </h3>
      <p class="text-xs text-on-surface-variant font-body mb-5">Created ${formatDate(p.created_at)}</p>

      <!-- Meta -->
      <div class="space-y-2.5 mb-5">
        <div class="flex justify-between items-center">
          <span class="text-[10px] uppercase tracking-wider font-bold text-on-surface-variant/60">Case ID</span>
          <span class="text-xs font-semibold text-primary font-body">${p.project_id.slice(0,8).toUpperCase()}</span>
        </div>
        <div class="flex justify-between items-center">
          <span class="text-[10px] uppercase tracking-wider font-bold text-on-surface-variant/60">Last Activity</span>
          <span class="text-xs font-semibold text-primary font-body">${timeAgo(p.created_at)}</span>
        </div>
      </div>

      <!-- Footer -->
      <div class="pt-4 border-t border-outline-variant/10 flex items-center justify-between">
        <span class="text-xs text-on-surface-variant font-body">Open project</span>
        <span class="material-symbols-outlined text-[18px] text-on-surface-variant/40 group-hover:text-secondary transition-colors">arrow_forward</span>
      </div>
    </div>`;
}

function renderEmptyState() {
  return `
    <div class="flex flex-col items-center justify-center py-24 text-center">
      <div class="w-16 h-16 bg-surface-container rounded-2xl flex items-center justify-center mb-6">
        <span class="material-symbols-outlined text-3xl text-on-surface-variant">folder_open</span>
      </div>
      <h3 class="font-headline font-bold text-xl text-primary mb-2">No projects yet</h3>
      <p class="text-on-surface-variant text-sm font-body mb-8">Create your first legal case to get started.</p>
      <button id="btn-empty-new"
        class="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gradient-to-b from-primary to-primary-container
               text-on-primary font-headline font-semibold text-sm hover:opacity-90 transition-opacity">
        <span class="material-symbols-outlined text-[18px]">add</span>
        New Project
      </button>
    </div>`;
}

function renderNewProjectModal() {
  return `
    <div id="modal-new-project" class="hidden fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/20 backdrop-blur-sm" id="modal-backdrop"></div>
      <div class="relative bg-surface-container-lowest rounded-2xl shadow-[0_32px_80px_-16px_rgba(0,0,0,0.18)] w-full max-w-md p-8 ring-1 ring-outline-variant/10">
        <h2 class="font-headline font-bold text-xl text-primary mb-1">New Project</h2>
        <p class="text-on-surface-variant text-sm font-body mb-6">Give your legal case a descriptive name.</p>

        <label class="block text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-1.5">Project Title</label>
        <input
          id="input-project-title"
          type="text"
          placeholder="e.g. Harrison v. Global Tech Solutions"
          class="w-full bg-surface-container ring-1 ring-outline-variant/20 focus:ring-2 focus:ring-secondary rounded-lg px-3.5 py-2.5 text-sm font-body outline-none transition-all mb-6"
        >

        <div id="modal-error" class="hidden text-sm text-error bg-error-container/40 rounded-lg px-3.5 py-2.5 font-body mb-4"></div>

        <div class="flex gap-3">
          <button id="btn-modal-cancel"
            class="flex-1 px-4 py-2.5 rounded-lg bg-surface-container text-on-surface font-headline font-semibold text-sm hover:bg-surface-container-high transition-colors">
            Cancel
          </button>
          <button id="btn-modal-create"
            class="flex-1 px-4 py-2.5 rounded-lg bg-gradient-to-b from-primary to-primary-container text-on-primary font-headline font-semibold text-sm hover:opacity-90 transition-opacity">
            Create
          </button>
        </div>
      </div>
    </div>`;
}

// ── Context menu for project cards ──────────────────────────
let _contextMenu = null;

function showContextMenu(x, y, projectId, title) {
  removeContextMenu();
  _contextMenu = document.createElement('div');
  _contextMenu.id = 'ctx-menu';
  _contextMenu.className = 'fixed z-[200] bg-surface-container-lowest rounded-xl shadow-[0_8px_32px_-8px_rgba(0,0,0,0.15)] ring-1 ring-outline-variant/10 overflow-hidden text-sm font-body w-44';
  _contextMenu.style.left = `${x}px`;
  _contextMenu.style.top  = `${y}px`;
  _contextMenu.innerHTML  = `
    <button class="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-surface-container transition-colors" id="ctx-open">
      <span class="material-symbols-outlined text-[16px]">open_in_new</span>Open
    </button>
    <button class="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-error-container/40 text-error transition-colors" id="ctx-delete">
      <span class="material-symbols-outlined text-[16px]">delete</span>Delete
    </button>`;
  document.body.appendChild(_contextMenu);

  document.getElementById('ctx-open')?.addEventListener('click', () => {
    removeContextMenu();
    window.location.hash = `/project/${projectId}`;
  });

  document.getElementById('ctx-delete')?.addEventListener('click', async () => {
    removeContextMenu();
    if (!confirm(`Delete "${title}"? This cannot be undone.`)) return;
    try {
      await deleteProject(projectId, appState.user.id);
      toast('Project deleted', 'success');
      await loadPortfolioContent();
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  setTimeout(() => document.addEventListener('click', removeContextMenu, { once: true }), 0);
}

function removeContextMenu() {
  _contextMenu?.remove();
  _contextMenu = null;
}

// ── Event bindings ───────────────────────────────────────────

function bindProjectCards() {
  // Card click → navigate
  document.querySelectorAll('.project-card').forEach(card => {
    card.addEventListener('click', (e) => {
      if (e.target.closest('.project-menu-btn')) return;
      const id = card.dataset.projectId;
      window.location.hash = `/project/${id}`;
    });
  });

  // Timeline card click
  document.querySelectorAll('[data-project]').forEach(el => {
    el.addEventListener('click', () => {
      window.location.hash = `/project/${el.dataset.project}`;
    });
  });

  // Context menu buttons
  document.querySelectorAll('.project-menu-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const rect = btn.getBoundingClientRect();
      showContextMenu(rect.left, rect.bottom + 4, btn.dataset.projectId, btn.dataset.title);
    });
  });

  // Empty state new project
  document.getElementById('btn-empty-new')?.addEventListener('click', () => {
    document.getElementById('modal-new-project')?.classList.remove('hidden');
    document.getElementById('input-project-title')?.focus();
  });
}

function bindPortfolioEvents() {
  // Modal cancel
  document.addEventListener('click', (e) => {
    if (e.target.id === 'modal-backdrop' || e.target.id === 'btn-modal-cancel') {
      document.getElementById('modal-new-project')?.classList.add('hidden');
    }
  });

  // Modal create
  document.addEventListener('click', async (e) => {
    if (e.target.id !== 'btn-modal-create') return;
    const titleInput = document.getElementById('input-project-title');
    const title      = titleInput?.value.trim();
    const errorEl    = document.getElementById('modal-error');
    errorEl?.classList.add('hidden');

    if (!title) {
      errorEl.textContent = 'Please enter a project title.';
      errorEl.classList.remove('hidden');
      return;
    }

    const btn = document.getElementById('btn-modal-create');
    btn.disabled = true;
    btn.textContent = 'Creating...';

    try {
      const project = await createProject(appState.user.id, title);
      toast('Project created', 'success');
      document.getElementById('modal-new-project')?.classList.add('hidden');
      titleInput.value = '';
      window.location.hash = `/project/${project.project_id}`;
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.remove('hidden');
      btn.disabled = false;
      btn.textContent = 'Create';
    }
  });

  // Enter key in title input
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.getElementById('modal-new-project')?.classList.add('hidden');
    }
    if (e.key === 'Enter' && e.target.id === 'input-project-title') {
      document.getElementById('btn-modal-create')?.click();
    }
  });
}
