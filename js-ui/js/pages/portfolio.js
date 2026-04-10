// ============================================================
// PORTFOLIO PAGE — projects overview (main page)
// Mirrors: ui/src/ui/ui_components/project_component.py
// ============================================================

import { loadProjects, deleteProject, streamProjectInit } from '../api.js';
import { renderMainSidebar, bindMainSidebarEvents }    from '../components/sidebar.js';
import { renderTopbar }                                from '../components/topbar.js';
import { renderPipelineModal, openPipelineModal }      from '../components/pipeline_modal.js';
import { appState }                                    from '../state.js';
import { formatDate, timeAgo, toast, skeleton, uuid, arrayBufferToBase64, resolveFileType, escHtml } from '../utils.js';
import { logger }                                      from '../logger.js';

const log = logger.child({ module: 'portfolio' });

export async function renderPortfolio() {
  const newProjectBtn = `
    <button id="btn-new-project"
      class="flex items-center gap-2 px-4 py-2 rounded-xl
             bg-gradient-to-b from-primary to-primary-container text-on-primary
             font-headline font-semibold text-sm hover:opacity-90 active:scale-[0.98] transition-all shadow-sm">
      <span class="material-symbols-outlined text-[16px]">add</span>
      New Project
    </button>`;

  const shell = `
    ${renderMainSidebar()}
    <div class="ml-64 min-h-screen bg-surface">
      ${renderTopbar({ title: 'Projects', actions: newProjectBtn })}
      <div id="portfolio-content" class="px-10 py-8">
        <div class="space-y-4">${skeleton(4)}</div>
      </div>
    </div>
    ${renderPipelineModal({
      id:              'init',
      icon:            'rocket_launch',
      title:           'New Project',
      description:     'Upload documents to initialise the factsheet',
      contextRequired: true,
      runLabel:        'Initialize Project',
    })}`;

  document.getElementById('app').innerHTML = shell;
  bindMainSidebarEvents();
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
    bindPortfolioSearch();
  } catch (err) {
    log.error({ err: err.message }, 'loadPortfolioContent feilet');
    container.innerHTML = `<p class="text-error text-sm font-body p-4">Feil: ${err.message}</p>`;
  }
}

function buildPortfolioHTML(projects) {
  if (!projects?.length) return renderEmptyState();

  const timelineHtml = buildTimeline(projects);
  const gridHtml     = buildProjectGrid(projects);

  return `
    <!-- Search -->
    <div class="mb-8">
      <div class="relative max-w-lg">
        <span class="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant text-[20px]">search</span>
        <input
          id="portfolio-search"
          type="text"
          placeholder="Search projects..."
          class="w-full bg-surface-container-lowest ring-1 ring-outline-variant/20 focus:ring-2 focus:ring-secondary rounded-xl py-3 pl-12 pr-4 text-sm font-body outline-none transition-all placeholder:text-on-surface-variant/50"
        >
      </div>
    </div>

    <!-- Project cards grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 mb-12">
      ${gridHtml}
    </div>

    <!-- Timeline -->
    ${timelineHtml}`;
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

  const partyNames  = (p.project_parties ?? []).map(pp => pp.legal_name ?? '').join(' ');
  const searchName  = [p.title ?? '', p.background ?? '', partyNames].join(' ').toLowerCase();

  return `
    <div class="group bg-surface-container-lowest hover:bg-white rounded-xl p-6 ring-1 ring-outline-variant/10
                hover:shadow-[0_20px_40px_-15px_rgba(0,0,0,0.07)] transition-all cursor-pointer project-card"
         data-project-id="${p.project_id}"
         data-search-name="${escHtml(searchName)}">

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
          <span class="text-xs font-semibold text-primary font-body font-mono">${p.project_id}</span>
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

// ── Search ───────────────────────────────────────────────────

function bindPortfolioSearch() {
  const input    = document.getElementById('portfolio-search');
  const timeline = document.querySelector('section.mb-4');
  if (!input) return;

  input.addEventListener('input', () => {
    const q = input.value.toLowerCase().trim();
    document.querySelectorAll('.project-card').forEach(card => {
      const hit = !q || (card.dataset.searchName ?? '').includes(q);
      card.style.display = hit ? '' : 'none';
    });
    // Hide portfolio timeline while searching — it only shows top-5 and can't be filtered easily
    if (timeline) timeline.style.display = q ? 'none' : '';
  });
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

  // Empty state new project button
  document.getElementById('btn-empty-new')?.addEventListener('click', _openNewProjectModal);
}

function bindPortfolioEvents() {
  document.getElementById('btn-new-project')?.addEventListener('click', _openNewProjectModal);
}

function _openNewProjectModal() {
  openPipelineModal('init', {
    contextRequired: true,
    onRun: async ({ files, question, model }, { logLine, setError, setDone, setAbort, onChunk }) => {
      const projectId = uuid();
      const queryId   = uuid();

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

      const ctrl = streamProjectInit(
        {
          question,
          attachments,
          session_id:  uuid(),
          llm_model:   model ?? 'google_gemini-2.5-flash',
          query_id:    queryId,
          project_id:  projectId,
        },
        {
          onChunk:  (e)   => onChunk(e),
          onDone:   ()    => {
            setDone('✅ Project created! Reloading...');
            toast('Project created', 'success');
            setTimeout(() => {
              window.location.hash = `/project/${projectId}`;
              window.location.reload();
            }, 1200);
          },
          onError:  (err) => setError(err.message),
        },
      );
      setAbort(ctrl);
    },
  });
}
