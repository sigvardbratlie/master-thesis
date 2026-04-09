// ============================================================
// USER SETTINGS PAGE
// Layout ref: new-ui/user_page.html
// Logic ref:  ui/src/ui/services/database_service.py (load/upsert user_details)
//             ui/src/ui/models.py (UserDetails)
// ============================================================

import { loadUserDetails, upsertUserDetails, loadAllCompanies } from '../api.js';
import { renderMainSidebar, bindMainSidebarEvents } from '../components/sidebar.js';
import { renderTopbar }                     from '../components/topbar.js';
import { appState }                         from '../state.js';
import { toast, skeleton, initials }        from '../utils.js';

export async function renderUser() {
  document.getElementById('app').innerHTML = `
    ${renderMainSidebar()}
    <div class="ml-64 min-h-screen bg-surface">
      ${renderTopbar({
        title: 'Profile & Settings',
        breadcrumb: { label: 'Projects', href: '#/' },
      })}
      <div id="user-content" class="px-10 py-8 max-w-3xl">
        <div class="space-y-4">${skeleton(4)}</div>
      </div>
    </div>`;

  bindMainSidebarEvents();

  try {
    const [details, companies] = await Promise.all([
      loadUserDetails(appState.user.id),
      loadAllCompanies(),
    ]);
    renderUserForm(details, companies);
  } catch (err) {
    document.getElementById('user-content').innerHTML =
      `<p class="text-error text-sm">${err.message}</p>`;
  }
}

function renderUserForm(details, companies) {
  const user        = appState.user;
  const firstName   = details?.user_first_name ?? '';
  const lastName    = details?.user_last_name  ?? '';
  const role        = details?.user_role       ?? '';
  const companyId   = details?.company_id      ?? '';
  const displayName = [firstName, lastName].filter(Boolean).join(' ') || user?.email?.split('@')[0] || '?';
  const ints        = initials(displayName);

  const companyOptions = companies.map(c =>
    `<option value="${c.company_id}" ${c.company_id === companyId ? 'selected' : ''}>${c.company_name ?? c.company_id}</option>`
  ).join('');

  document.getElementById('user-content').innerHTML = `

    <!-- Avatar + name header -->
    <div class="flex items-center gap-6 mb-10">
      <div class="w-20 h-20 rounded-2xl bg-primary-container flex items-center justify-center flex-shrink-0 shadow-[0_8px_24px_-8px_rgba(8,25,66,0.25)]">
        <span class="font-headline font-black text-2xl text-on-primary">${ints}</span>
      </div>
      <div>
        <h1 class="font-headline font-black text-3xl text-primary leading-none">${displayName}</h1>
        <p class="text-on-surface-variant text-sm font-body mt-1">${user?.email ?? ''}</p>
        <span class="mt-2 inline-block px-2.5 py-0.5 rounded-full bg-secondary-container/30 text-on-secondary-container text-xs font-bold uppercase tracking-wide">
          ${role || 'No role set'}
        </span>
      </div>
    </div>

    <!-- Form card -->
    <div class="bg-surface-container-lowest rounded-2xl p-8 ring-1 ring-outline-variant/10 shadow-[0_4px_24px_-8px_rgba(0,0,0,0.05)] mb-6">
      <h2 class="font-headline font-bold text-lg text-primary mb-6">Personal Information</h2>

      <form id="user-form" class="space-y-5">
        <div class="grid grid-cols-2 gap-5">
          ${field('First Name',  'user_first_name', firstName,  'text', 'e.g. Sigvard')}
          ${field('Last Name',   'user_last_name',  lastName,   'text', 'e.g. Bratlie')}
        </div>

        ${field('Role / Title', 'user_role', role, 'text', 'e.g. Senior Partner, Associate')}

        <div>
          <label class="block text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-1.5">
            Company
          </label>
          <select id="user_company_id"
            class="w-full bg-surface-container ring-1 ring-outline-variant/20 focus:ring-2 focus:ring-secondary rounded-lg px-3.5 py-2.5 text-sm font-body outline-none transition-all">
            <option value="">— No company —</option>
            ${companyOptions}
          </select>
        </div>

        <div id="user-form-error" class="hidden text-sm text-error bg-error-container/40 rounded-lg px-3.5 py-2.5 font-body"></div>

        <div class="pt-2 flex items-center gap-3">
          <button type="submit" id="btn-save-user"
            class="flex items-center gap-2 px-6 py-2.5 rounded-lg bg-gradient-to-b from-primary to-primary-container
                   text-on-primary font-headline font-semibold text-sm hover:opacity-90 transition-opacity">
            <span class="material-symbols-outlined text-[18px]">save</span>
            Save Changes
          </button>
          <span id="save-success" class="hidden text-sm text-green-600 font-semibold flex items-center gap-1">
            <span class="material-symbols-outlined text-[18px]">check_circle</span>Saved
          </span>
        </div>
      </form>
    </div>

    <!-- Account info card (read-only) -->
    <div class="bg-surface-container-lowest rounded-2xl p-8 ring-1 ring-outline-variant/10 shadow-[0_4px_24px_-8px_rgba(0,0,0,0.05)]">
      <h2 class="font-headline font-bold text-lg text-primary mb-6">Account</h2>
      <div class="space-y-4">
        <div class="flex justify-between items-center py-3 border-b border-outline-variant/10">
          <div>
            <p class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Email</p>
            <p class="text-sm font-semibold text-on-surface mt-0.5">${user?.email ?? '—'}</p>
          </div>
          <span class="px-2.5 py-0.5 rounded-full bg-surface-container text-on-surface-variant text-xs font-bold">Verified</span>
        </div>
        <div class="flex justify-between items-center py-3 border-b border-outline-variant/10">
          <div>
            <p class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">User ID</p>
            <p class="text-xs font-mono text-on-surface-variant mt-0.5">${user?.id ?? '—'}</p>
          </div>
        </div>
        <div class="flex justify-between items-center py-3">
          <div>
            <p class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Member Since</p>
            <p class="text-sm font-semibold text-on-surface mt-0.5">
              ${user?.created_at ? new Date(user.created_at).toLocaleDateString('no-NO', { year: 'numeric', month: 'long' }) : '—'}
            </p>
          </div>
        </div>
      </div>
    </div>`;

  // Bind form submit
  document.getElementById('user-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn     = document.getElementById('btn-save-user');
    const errorEl = document.getElementById('user-form-error');
    const successEl = document.getElementById('save-success');
    errorEl?.classList.add('hidden');
    successEl?.classList.add('hidden');
    btn.disabled = true;

    const payload = {
      user_id:         appState.user.id,
      user_first_name: document.getElementById('user_first_name')?.value.trim() || null,
      user_last_name:  document.getElementById('user_last_name')?.value.trim()  || null,
      user_role:       document.getElementById('user_role')?.value.trim()       || null,
      company_id:      document.getElementById('user_company_id')?.value        || null,
    };

    try {
      await upsertUserDetails(payload);
      // Refresh appState.userDetails
      appState.userDetails = payload;
      successEl?.classList.remove('hidden');
      setTimeout(() => successEl?.classList.add('hidden'), 2500);
      toast('Profile saved', 'success');
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl?.classList.remove('hidden');
    } finally {
      btn.disabled = false;
    }
  });
}

function field(label, id, value, type = 'text', placeholder = '') {
  return `
    <div>
      <label for="${id}" class="block text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-1.5">
        ${label}
      </label>
      <input
        id="${id}"
        type="${type}"
        value="${value}"
        placeholder="${placeholder}"
        class="w-full bg-surface-container ring-1 ring-outline-variant/20 focus:ring-2 focus:ring-secondary
               rounded-lg px-3.5 py-2.5 text-sm font-body outline-none transition-all"
      >
    </div>`;
}
