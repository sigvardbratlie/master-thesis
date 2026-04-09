// ============================================================
// SIDEBAR LEVEL 2 — project-specific navigation
// Rendered when a project is selected (#/project/:id)
// ============================================================

import { authService } from '../auth.js';

export function renderProjectSidebar(projectId) {
  const current = window.location.hash.slice(1) || '';

  function link(icon, label, path, filled = false) {
    const isActive = current === path || current.startsWith(path + '/');
    const fillAttr = filled && isActive ? `style="font-variation-settings:'FILL' 1"` : '';
    return `
      <a href="#${path}" class="flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm transition-all
        ${isActive
          ? 'bg-surface-container-lowest text-primary font-bold shadow-sm translate-x-0.5'
          : 'text-on-surface-variant hover:bg-surface-container-lowest/60 hover:text-primary'
        }">
        <span class="material-symbols-outlined text-[20px]" ${fillAttr}>${icon}</span>
        <span>${label}</span>
      </a>`;
  }

  return `
    <aside id="sidebar" class="h-screen w-64 fixed left-0 top-0 z-50 bg-surface-container-low flex flex-col py-6 px-4 font-body text-sm">

      <!-- Brand -->
      <div class="mb-8 px-2">
        <h1 class="font-headline font-black text-primary-container text-xl uppercase tracking-widest leading-none">The Editorial</h1>
        <span class="text-[10px] text-on-surface-variant font-bold uppercase tracking-[0.18em]">Legal Curator</span>
      </div>

      <!-- Primary nav -->
      <nav class="flex-1 space-y-0.5 overflow-y-auto">
        ${link('dashboard', 'Dashboard', `/project/${projectId}`, true)}
        ${link('chat', 'Chat', `/chat/${projectId}`, true)}
        ${link('calendar_today', 'Calendar', `/calendar/${projectId}`)}

        <!-- Tools -->
        <div class="mt-6 mb-1.5 px-4">
          <p class="text-[9px] font-bold text-on-surface-variant/40 uppercase tracking-[0.15em]">Tools</p>
        </div>
        ${link('edit_note', 'Document Edit', `/tools/edit/${projectId}`)}
        ${link('layers', 'Batch Edit', `/tools/batch/${projectId}`)}
        ${link('table_chart', 'Tabular Extraction', `/tools/table/${projectId}`)}
        ${link('event_repeat', 'Lovdata', `/tools/lovdata/${projectId}`)}
      </nav>

      <!-- Update Project + footer -->
      <div class="mt-4 space-y-3">
        <button id="btn-update-project"
          class="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl
                 bg-gradient-to-b from-primary to-primary-container text-on-primary
                 font-headline font-semibold text-sm hover:opacity-90 active:scale-[0.98] transition-all shadow-sm">
          <span class="material-symbols-outlined text-[18px]">sync</span>
          Update Project
        </button>
        <div class="pt-3 border-t border-outline-variant/15 space-y-0.5">
          <a href="#/user"
            class="flex items-center gap-3 px-4 py-2 text-sm text-on-surface-variant hover:bg-surface-container-lowest/60 hover:text-primary rounded-lg transition-colors">
            <span class="material-symbols-outlined text-[18px]">settings</span>Settings
          </a>
          <button id="btn-logout-proj"
            class="w-full flex items-center gap-3 px-4 py-2 text-sm text-on-surface-variant hover:bg-surface-container-lowest/60 rounded-lg transition-colors text-left">
            <span class="material-symbols-outlined text-[18px]">logout</span>Sign Out
          </button>
        </div>
      </div>
    </aside>`;
}

export function bindProjectSidebarEvents({ onUpdate } = {}) {
  document.getElementById('btn-update-project')?.addEventListener('click', () => {
    onUpdate?.();
  });
  document.getElementById('btn-logout-proj')?.addEventListener('click', async () => {
    await authService.logout();
    window.location.reload();
  });
}
