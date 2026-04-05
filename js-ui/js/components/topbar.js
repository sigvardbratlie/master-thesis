// ============================================================
// TOPBAR — sticky top navigation bar
// ============================================================

export function renderTopbar({ title = '', breadcrumb = null, actions = '' } = {}) {
  return `
    <header class="sticky top-0 z-40 bg-surface/80 backdrop-blur-sm flex items-center justify-between px-8 py-3.5 border-b border-outline-variant/10">

      <!-- Left: title / breadcrumb -->
      <div class="flex items-center gap-3">
        ${breadcrumb ? `
          <a href="${breadcrumb.href}" class="text-on-surface-variant hover:text-primary transition-colors text-sm font-medium">
            ${breadcrumb.label}
          </a>
          <span class="material-symbols-outlined text-[16px] text-on-surface-variant/40">chevron_right</span>
        ` : ''}
        <h2 class="text-base font-headline font-bold text-primary leading-none">${title}</h2>
      </div>

      <!-- Right: search + actions -->
      <div class="flex items-center gap-4">

        <!-- Global search -->
        <div class="relative group">
          <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-[18px] group-focus-within:text-secondary transition-colors">search</span>
          <input
            id="global-search"
            type="text"
            placeholder="Search projects..."
            class="w-52 bg-surface-container ring-1 ring-outline-variant/20 focus:ring-secondary/50 focus:ring-2 rounded-lg pl-9 pr-3 py-1.5 text-sm font-body outline-none transition-all placeholder:text-on-surface-variant/50"
          >
        </div>

        <!-- Notifications -->
        <button class="p-1.5 rounded-lg text-on-surface-variant hover:bg-surface-container transition-colors">
          <span class="material-symbols-outlined text-[20px]">notifications</span>
        </button>

        <!-- Extra actions slot -->
        ${actions}
      </div>
    </header>`;
}
