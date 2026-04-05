// ============================================================
// LOGIN PAGE
// ============================================================

import { authService } from '../auth.js';
import { toast }       from '../utils.js';

export function renderLogin() {
  document.getElementById('app').innerHTML = `
    <div class="min-h-screen bg-surface flex items-center justify-center px-4">
      <div class="w-full max-w-sm">

        <!-- Logo -->
        <div class="text-center mb-10">
          <div class="inline-flex items-center justify-center w-14 h-14 bg-primary-container rounded-2xl mb-5 shadow-[0_8px_32px_-8px_rgba(8,25,66,0.3)]">
            <span class="material-symbols-outlined text-white text-2xl" style="font-variation-settings:'FILL' 1">gavel</span>
          </div>
          <h1 class="font-headline font-black text-3xl text-primary leading-none">The Curator</h1>
          <p class="text-on-surface-variant text-sm mt-2 font-body">Legal Case Management</p>
        </div>

        <!-- Form card -->
        <div class="bg-surface-container-lowest rounded-2xl p-8 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.08)]">
          <h2 class="font-headline font-bold text-lg text-primary mb-6">Sign in</h2>

          <form id="login-form" class="space-y-4">
            <div>
              <label class="block text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-1.5">
                Email
              </label>
              <input
                id="login-email"
                type="email"
                autocomplete="email"
                required
                class="w-full bg-surface-container ring-1 ring-outline-variant/20 focus:ring-2 focus:ring-secondary rounded-lg px-3.5 py-2.5 text-sm font-body outline-none transition-all"
                placeholder="name@lawfirm.com"
              >
            </div>

            <div>
              <label class="block text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-1.5">
                Password
              </label>
              <input
                id="login-password"
                type="password"
                autocomplete="current-password"
                required
                class="w-full bg-surface-container ring-1 ring-outline-variant/20 focus:ring-2 focus:ring-secondary rounded-lg px-3.5 py-2.5 text-sm font-body outline-none transition-all"
                placeholder="••••••••"
              >
            </div>

            <div id="login-error" class="hidden text-sm text-error bg-error-container/40 rounded-lg px-3.5 py-2.5 font-body"></div>

            <button
              type="submit"
              id="btn-login"
              class="w-full mt-2 flex items-center justify-center gap-2 px-4 py-3 rounded-lg
                     bg-gradient-to-b from-primary to-primary-container text-on-primary
                     font-headline font-semibold text-sm hover:opacity-90 transition-opacity shadow-sm">
              <span id="btn-login-label">Sign in</span>
              <span id="btn-login-spinner" class="hidden">
                <svg class="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                </svg>
              </span>
            </button>
          </form>
        </div>

        <p class="text-center text-xs text-on-surface-variant mt-6 font-body">
          Powered by <span class="font-semibold">The Editorial Authority</span>
        </p>
      </div>
    </div>`;

  // Bind events
  document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const email    = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;
    const errorEl  = document.getElementById('login-error');
    const btn      = document.getElementById('btn-login');
    const label    = document.getElementById('btn-login-label');
    const spinner  = document.getElementById('btn-login-spinner');

    errorEl.classList.add('hidden');
    btn.disabled = true;
    label.textContent = 'Signing in...';
    spinner.classList.remove('hidden');

    try {
      await authService.login(email, password);
      // onAuthStateChange in app.js will handle the redirect
    } catch (err) {
      errorEl.textContent = err.message ?? 'Login failed. Check your credentials.';
      errorEl.classList.remove('hidden');
      btn.disabled = false;
      label.textContent = 'Sign in';
      spinner.classList.add('hidden');
    }
  });
}
