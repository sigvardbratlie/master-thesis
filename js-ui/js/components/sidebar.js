// ============================================================
// SIDEBAR — persistent left navigation
// ============================================================

import { router }      from '../router.js';
import { authService } from '../auth.js';
import { appState }    from '../state.js';

const NAV_ITEMS = [
  { icon: 'folder_open',    label: 'Projects',  path: '/'        },
  { icon: 'chat',           label: 'Chat',      path: '/chat'    },
  { icon: 'calendar_today', label: 'Calendar',  path: '/calendar'},
  { icon: 'domain',         label: 'Company',   path: '/company' },
  { icon: 'manage_accounts',label: 'Settings',  path: '/user'    },
];

const BOTTOM_ITEMS = [
  { icon: 'contact_support', label: 'Support', path: '/support' },
  { icon: 'inventory_2',     label: 'Archive', path: '/archive' },
];

export function renderSidebar() {
  const current = window.location.hash.slice(1) || '/';

  function navLink({ icon, label, path }) {
    const isActive = current === path || (path !== '/' && current.startsWith(path));
    return `
      <a href="#${path}" class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all
        ${isActive
          ? 'bg-surface-container-lowest text-primary font-semibold shadow-sm'
          : 'text-on-surface-variant hover:text-primary hover:bg-surface-container-lowest/60'
        }">
        <span class="material-symbols-outlined text-[20px]">${icon}</span>
        <span>${label}</span>
      </a>`;
  }

  const user = appState.user;
  const details = appState.userDetails;
  const displayName = [details?.user_first_name, details?.user_last_name].filter(Boolean).join(' ')
    || user?.email?.split('@')[0] || 'User';

  return `
    <aside id="sidebar" class="h-screen w-64 fixed left-0 top-0 z-50 bg-surface-container-low flex flex-col p-6 font-body text-sm">

      <!-- Logo -->
      <div class="mb-10">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 bg-primary-container rounded-lg flex items-center justify-center flex-shrink-0">
            <span class="material-symbols-outlined text-white text-[18px]" style="font-variation-settings:'FILL' 1">gavel</span>
          </div>
          <div>
            <h1 class="font-headline font-black text-primary-container text-base leading-none">The Curator</h1>
            <p class="text-[10px] uppercase tracking-widest text-on-surface-variant mt-0.5">Legal Authority</p>
          </div>
        </div>
      </div>

      <!-- New Project button -->
      <button id="btn-new-project"
        class="w-full mb-6 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg
               bg-gradient-to-b from-primary to-primary-container text-on-primary text-sm font-headline font-semibold
               hover:opacity-90 transition-opacity shadow-sm">
        <span class="material-symbols-outlined text-[18px]">add</span>
        New Project
      </button>

      <!-- Nav -->
      <nav class="flex-1 space-y-0.5">
        ${NAV_ITEMS.map(navLink).join('')}
      </nav>

      <!-- Bottom -->
      <div class="space-y-0.5 pt-6 border-t border-outline-variant/15">
        ${BOTTOM_ITEMS.map(navLink).join('')}

        <!-- User avatar row -->
        <button id="btn-user-menu"
          class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-surface-container-lowest/60 transition-colors mt-2 text-left">
          <div class="w-8 h-8 rounded-full bg-primary-container flex items-center justify-center flex-shrink-0">
            <span class="text-on-primary text-xs font-bold">
              ${displayName.split(' ').map(p => p[0]).join('').toUpperCase().slice(0,2) || '?'}
            </span>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-sm font-semibold text-on-surface truncate">${displayName}</p>
            <p class="text-[10px] text-on-surface-variant truncate">${user?.email ?? ''}</p>
          </div>
          <span class="material-symbols-outlined text-[16px] text-on-surface-variant">more_vert</span>
        </button>
      </div>

      <!-- User dropdown (hidden by default) -->
      <div id="user-dropdown"
        class="hidden absolute bottom-20 left-4 right-4 bg-surface-container-lowest rounded-xl shadow-[0_8px_32px_-8px_rgba(0,0,0,0.12)] ring-1 ring-outline-variant/10 overflow-hidden z-10">
        <a href="#/user" class="flex items-center gap-3 px-4 py-3 text-sm hover:bg-surface-container transition-colors">
          <span class="material-symbols-outlined text-[18px]">manage_accounts</span>Profile
        </a>
        <button id="btn-logout"
          class="w-full flex items-center gap-3 px-4 py-3 text-sm text-error hover:bg-error-container/30 transition-colors">
          <span class="material-symbols-outlined text-[18px]">logout</span>Sign out
        </button>
      </div>

    </aside>`;
}

export function bindSidebarEvents() {
  // New project modal trigger
  document.getElementById('btn-new-project')?.addEventListener('click', () => {
    document.getElementById('modal-new-project')?.classList.remove('hidden');
    document.getElementById('input-project-title')?.focus();
  });

  // User dropdown toggle
  document.getElementById('btn-user-menu')?.addEventListener('click', (e) => {
    e.stopPropagation();
    document.getElementById('user-dropdown')?.classList.toggle('hidden');
  });
  document.addEventListener('click', () => {
    document.getElementById('user-dropdown')?.classList.add('hidden');
  }, { once: false });

  // Logout
  document.getElementById('btn-logout')?.addEventListener('click', async () => {
    await authService.logout();
    window.location.reload();
  });
}
