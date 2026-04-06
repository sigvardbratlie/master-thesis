// ── Non-sensitive (safe to commit) ──────────────────────────
export const APP_CONFIG = {
  appName:    'The Curator',
  appVersion: '0.1.0',
};

// ── Sensitive — loaded from .env via Vite ────────────────────
// Verdier i .env:  VITE_SUPABASE_URL, VITE_SUPABASE_KEY, VITE_BACKEND_URL
// Vite eksponerer kun VITE_-prefixede variabler til browser-bundle.
export const CONFIG = {
  supabaseUrl: import.meta.env.VITE_SUPABASE_URL,
  supabaseKey: import.meta.env.VITE_SUPABASE_KEY,
  backendUrl:  import.meta.env.VITE_BACKEND_URL ?? 'http://localhost:8080',
};
