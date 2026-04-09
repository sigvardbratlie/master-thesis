// ============================================================
// APP — entry point, bootstrap, auth guard, routing
// ============================================================

import { authService }      from './auth.js';
import { router }           from './router.js';
import { loadUserDetails }  from './api.js';
import { appState }         from './state.js';
import { renderLogin }      from './pages/login.js';
import { renderPortfolio }  from './pages/portfolio.js';
import { renderDashboard }  from './pages/dashboard.js';
import { renderProject }    from './pages/project.js';
import { renderChat }       from './pages/chat.js';
import { renderCalendar }   from './pages/calendar.js';
import { renderUser }       from './pages/user.js';
import { renderCompany }    from './pages/company.js';

export { appState };

// ── Bootstrap ─────────────────────────────────────────────────
async function bootstrap() {
  // Show loading indicator
  document.getElementById('app').innerHTML = `
    <div class="min-h-screen bg-surface flex items-center justify-center">
      <div class="flex flex-col items-center gap-4">
        <div class="w-12 h-12 bg-primary-container rounded-2xl flex items-center justify-center">
          <span class="material-symbols-outlined text-white text-xl" style="font-variation-settings:'FILL' 1">gavel</span>
        </div>
        <div class="flex gap-1">
          <span class="w-1.5 h-1.5 bg-secondary rounded-full animate-bounce" style="animation-delay:0ms"></span>
          <span class="w-1.5 h-1.5 bg-secondary rounded-full animate-bounce" style="animation-delay:150ms"></span>
          <span class="w-1.5 h-1.5 bg-secondary rounded-full animate-bounce" style="animation-delay:300ms"></span>
        </div>
      </div>
    </div>`;

  // Check existing session
  const session = await authService.getSession();

  if (session) {
    await hydrateAppState(session);
    setupRouter();
    router.start();
  } else {
    renderLogin();
  }

  // Listen for auth changes (login / logout)
  authService.onAuthStateChange(async (event, session) => {
    if (event === 'SIGNED_IN' && session) {
      await hydrateAppState(session);
      setupRouter();
      // Navigate to portfolio if on login screen
      if (!window.location.hash || window.location.hash === '#/') {
        router.navigate('/');
      } else {
        router.start();
      }
    } else if (event === 'SIGNED_OUT') {
      appState.user        = null;
      appState.userDetails = null;
      renderLogin();
    }
  });
}

async function hydrateAppState(session) {
  appState.user = session.user;
  try {
    appState.userDetails = await loadUserDetails(session.user.id);
  } catch {
    appState.userDetails = null;
  }
}

function setupRouter() {
  router
    .on('/dashboard',     ()       => renderDashboard())
    .on('/',              ()       => renderPortfolio())
    .on('/project/:id',  (params) => renderProject(params))
    .on('/chat',          ()       => renderChat({}))
    .on('/chat/:id',     (params) => renderChat(params))
    .on('/calendar/:id',(params) => renderCalendar(params))
    .on('/user',          ()       => renderUser())
    .on('/company',       ()       => renderCompany())
    .on('/.*',            ()       => renderPortfolio());
}

// ── Start ─────────────────────────────────────────────────────
bootstrap();
