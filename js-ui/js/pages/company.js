// ============================================================
// COMPANY PAGE
// Layout ref: new-ui/company_page.html
// Logic ref:  ui/src/ui/services/database_service.py (load/upsert company_details)
//             ui/src/ui/models.py (CompanyDetails)
// ============================================================

import { loadUserDetails, loadCompanyDetails, upsertCompanyDetails, loadAllCompanies } from '../api.js';
import { renderSidebar, bindSidebarEvents } from '../components/sidebar.js';
import { renderTopbar }                     from '../components/topbar.js';
import { appState }                         from '../state.js';
import { toast, skeleton, initials }        from '../utils.js';

export async function renderCompany() {
  document.getElementById('app').innerHTML = `
    ${renderSidebar()}
    <div class="ml-64 min-h-screen bg-surface">
      ${renderTopbar({
        title: 'Company',
        breadcrumb: { label: 'Projects', href: '#/' },
      })}
      <div id="company-content" class="px-10 py-8 max-w-3xl">
        <div class="space-y-4">${skeleton(4)}</div>
      </div>
    </div>`;

  bindSidebarEvents();

  try {
    const userDetails = await loadUserDetails(appState.user.id);
    const companyId   = userDetails?.company_id;

    let company = null;
    if (companyId) company = await loadCompanyDetails(companyId);

    renderCompanyContent(company, companyId);
  } catch (err) {
    document.getElementById('company-content').innerHTML =
      `<p class="text-error text-sm">${err.message}</p>`;
  }
}

function renderCompanyContent(company, companyId) {
  const name   = company?.company_name ?? '';
  const vat    = company?.company_vat_nr ?? '';
  const cid    = company?.company_id ?? companyId ?? '';
  const ints   = name ? initials(name) : '?';

  document.getElementById('company-content').innerHTML = `

    <!-- Header -->
    <div class="flex items-center gap-6 mb-10">
      <div class="w-20 h-20 rounded-2xl bg-primary-container flex items-center justify-center flex-shrink-0 shadow-[0_8px_24px_-8px_rgba(8,25,66,0.25)]">
        <span class="material-symbols-outlined text-3xl text-on-primary" style="font-variation-settings:'FILL' 1">domain</span>
      </div>
      <div>
        <h1 class="font-headline font-black text-3xl text-primary leading-none">
          ${name || 'Your Company'}
        </h1>
        ${vat ? `<p class="text-on-surface-variant text-sm font-body mt-1">VAT: ${vat}</p>` : ''}
        ${cid ? `<p class="text-xs font-mono text-on-surface-variant/60 mt-1">${cid}</p>` : ''}
      </div>
    </div>

    ${!company ? `
    <div class="mb-6 p-4 bg-tertiary-fixed/20 rounded-xl ring-1 ring-tertiary-fixed-dim/30 flex items-start gap-3">
      <span class="material-symbols-outlined text-tertiary-fixed-dim text-[20px] mt-0.5">info</span>
      <p class="text-sm font-body text-on-surface">
        No company is associated with your account yet. You can create one below or ask your administrator to invite you.
      </p>
    </div>` : ''}

    <!-- Company details form -->
    <div class="bg-surface-container-lowest rounded-2xl p-8 ring-1 ring-outline-variant/10 shadow-[0_4px_24px_-8px_rgba(0,0,0,0.05)] mb-6">
      <h2 class="font-headline font-bold text-lg text-primary mb-6">
        ${company ? 'Company Details' : 'Create Company'}
      </h2>

      <form id="company-form" class="space-y-5">
        <div>
          <label for="company_name" class="block text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-1.5">
            Company Name
          </label>
          <input
            id="company_name"
            type="text"
            value="${name}"
            placeholder="e.g. Bratlie Legal Partners AS"
            class="w-full bg-surface-container ring-1 ring-outline-variant/20 focus:ring-2 focus:ring-secondary rounded-lg px-3.5 py-2.5 text-sm font-body outline-none transition-all"
          >
        </div>

        <div>
          <label for="company_vat" class="block text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-1.5">
            VAT / Org. Number
          </label>
          <input
            id="company_vat"
            type="text"
            value="${vat}"
            placeholder="e.g. 912 345 678 MVA"
            class="w-full bg-surface-container ring-1 ring-outline-variant/20 focus:ring-2 focus:ring-secondary rounded-lg px-3.5 py-2.5 text-sm font-body outline-none transition-all"
          >
        </div>

        <div id="company-form-error" class="hidden text-sm text-error bg-error-container/40 rounded-lg px-3.5 py-2.5 font-body"></div>

        <div class="pt-2 flex items-center gap-3">
          <button type="submit" id="btn-save-company"
            class="flex items-center gap-2 px-6 py-2.5 rounded-lg bg-gradient-to-b from-primary to-primary-container
                   text-on-primary font-headline font-semibold text-sm hover:opacity-90 transition-opacity">
            <span class="material-symbols-outlined text-[18px]">save</span>
            ${company ? 'Save Changes' : 'Create Company'}
          </button>
          <span id="company-save-success" class="hidden text-sm text-green-600 font-semibold flex items-center gap-1">
            <span class="material-symbols-outlined text-[18px]">check_circle</span>Saved
          </span>
        </div>
      </form>
    </div>

    <!-- Company info table (read-only) -->
    ${company ? `
    <div class="bg-surface-container-lowest rounded-2xl p-8 ring-1 ring-outline-variant/10 shadow-[0_4px_24px_-8px_rgba(0,0,0,0.05)]">
      <h2 class="font-headline font-bold text-lg text-primary mb-6">System Info</h2>
      <div class="space-y-4">
        <div class="flex justify-between items-center py-3 border-b border-outline-variant/10">
          <p class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Company ID</p>
          <p class="text-xs font-mono text-on-surface-variant">${cid}</p>
        </div>
        <div class="flex justify-between items-center py-3">
          <p class="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Status</p>
          <span class="px-2.5 py-0.5 rounded-full bg-secondary-container/30 text-on-secondary-container text-xs font-bold">Active</span>
        </div>
      </div>
    </div>` : ''}`;

  // Bind form submit
  document.getElementById('company-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn       = document.getElementById('btn-save-company');
    const errorEl   = document.getElementById('company-form-error');
    const successEl = document.getElementById('company-save-success');
    errorEl?.classList.add('hidden');
    successEl?.classList.add('hidden');
    btn.disabled = true;

    const companyName = document.getElementById('company_name')?.value.trim();
    const companyVat  = document.getElementById('company_vat')?.value.trim();

    if (!companyName) {
      errorEl.textContent = 'Company name is required.';
      errorEl?.classList.remove('hidden');
      btn.disabled = false;
      return;
    }

    // If no existing company, generate new UUID
    const payload = {
      company_id:      cid || crypto.randomUUID(),
      company_name:    companyName || null,
      company_vat_nr:  companyVat  || null,
    };

    try {
      await upsertCompanyDetails(payload);
      successEl?.classList.remove('hidden');
      setTimeout(() => successEl?.classList.add('hidden'), 2500);
      toast('Company saved', 'success');

      // Re-render with updated data
      renderCompanyContent(payload, payload.company_id);
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl?.classList.remove('hidden');
    } finally {
      btn.disabled = false;
    }
  });
}
