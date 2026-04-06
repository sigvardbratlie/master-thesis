// ============================================================
// AUTH — mirrors ui/src/ui/services/auth_service.py
// Uses Supabase JS v2. Session (access + refresh token) is
// stored in localStorage by Supabase automatically.
// Tokens are refreshed silently before expiry.
// ============================================================

import { CONFIG }   from './config.js';
import { authLog }  from './logger.js';
import { createClient } from '@supabase/supabase-js';

class AuthService {
  constructor() {
    this._client = createClient(CONFIG.supabaseUrl, CONFIG.supabaseKey, {
      auth: {
        persistSession: true,        // store in localStorage
        autoRefreshToken: true,      // silent refresh before expiry
        detectSessionInUrl: true,    // handle OAuth/magic-link callbacks
      },
    });
    this._listeners = [];
  }

  get client() {
    return this._client;
  }

  /** Login with email + password */
  async login(email, password) {
    authLog.info({ email }, 'Attempting login');
    const { data, error } = await this._client.auth.signInWithPassword({ email, password });
    if (error) { authLog.error({ err: error.message }, 'Login failed'); throw error; }
    authLog.info({ userId: data.user?.id }, 'Login successful');
    return data;
  }

  /** Logout — clears localStorage session */
  async logout() {
    await this._client.auth.signOut();
  }

  /**
   * Get current session. Returns null if not logged in.
   * Supabase refreshes token automatically if needed.
   */
  async getSession() {
    const { data: { session } } = await this._client.auth.getSession();
    return session;
  }

  /** Get the access token for Bearer auth to FastAPI */
  async getAccessToken() {
    const session = await this.getSession();
    return session?.access_token ?? null;
  }

  /** Get current user object */
  async getUser() {
    const { data: { user } } = await this._client.auth.getUser();
    return user;
  }

  /** Subscribe to auth state changes (SIGNED_IN / SIGNED_OUT) */
  onAuthStateChange(callback) {
    const { data: { subscription } } = this._client.auth.onAuthStateChange(callback);
    return subscription; // caller can call subscription.unsubscribe()
  }
}

// Singleton
export const authService = new AuthService();
