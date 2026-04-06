// ============================================================
// API — mirrors ui/src/ui/services/database_service.py
// Combines direct Supabase queries + FastAPI backend calls.
// ============================================================

import { CONFIG }      from './config.js';
import { authService } from './auth.js';
import { cache }       from './cache.js';
import { apiLog }      from './logger.js';

const TTL = {
  projects:     120_000,  // 2 min
  project:       60_000,  // 1 min
  userDetails:  300_000,  // 5 min
  company:      300_000,  // 5 min
  sessions:      60_000,  // 1 min
};

// ── Supabase DB shorthand ────────────────────────────────────
const db = () => authService.client.from.bind(authService.client);

// ── Fetch helper for FastAPI ─────────────────────────────────
async function apiFetch(path, options = {}) {
  const token = await authService.getAccessToken();
  const res = await fetch(`${CONFIG.backendUrl}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...(options.headers ?? {}),
    },
  });
  if (!res.ok) throw new Error(`API ${path} → ${res.status} ${res.statusText}`);
  return res;
}

// ── Projects ─────────────────────────────────────────────────

export async function loadProjects(userId) {
  const cacheKey = `projects:${userId}`;
  const cached = cache.get(cacheKey);
  if (cached) {
    apiLog.debug({ count: cached.length }, 'loadProjects — cache hit');
    return cached;
  }

  apiLog.debug({ userId }, 'loadProjects — spør Supabase');

  const { data, error, status, statusText } = await authService.client
    .from('projects')
    .select('project_id, title, created_at')
    .eq('user_id', userId)
    .order('created_at', { ascending: false });

  if (error) {
    apiLog.error({ err: error.message, code: error.code, status }, 'loadProjects feilet');
    throw error;
  }

  apiLog.info({ count: data.length, status }, 'loadProjects OK');
  cache.set(cacheKey, data, TTL.projects);
  return data;
}

export async function loadProject(projectId) {
  const cacheKey = `project:${projectId}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const { data, error } = await authService.client
    .from('projects')
    .select(`
      *,
      project_attachments(file_id, file_date, filename, file_type, path, created_at),
      project_events(*),
      project_parties(*),
      project_deadlines(*),
      project_damages(*),
      project_claims(*),
      project_emails(email_id, from_addr, to, cc, bcc, subject, body, date, message_id, created_at, path)
    `)
    .eq('project_id', projectId)
    .single();

  if (error) throw error;

  const result = {
    factsheet: {
      ...data,
      parties:   data.project_parties   ?? [],
      events:    data.project_events    ?? [],
      deadlines: data.project_deadlines ?? [],
      damages:   data.project_damages   ?? [],
      claims:    data.project_claims    ?? [],
    },
    attachments: data.project_attachments ?? [],
    emails:      data.project_emails      ?? [],
  };
  // clean up nested keys from factsheet
  ['project_parties','project_events','project_deadlines','project_damages',
   'project_claims','project_attachments','project_emails'].forEach(k => delete result.factsheet[k]);

  cache.set(cacheKey, result, TTL.project);
  return result;
}

export async function createProject(userId, title) {
  const { data, error } = await authService.client
    .from('projects')
    .insert({ user_id: userId, title })
    .select('project_id, title, created_at')
    .single();
  if (error) throw error;
  cache.invalidatePrefix(`projects:${userId}`);
  return data;
}

export async function deleteProject(projectId, userId) {
  const { error } = await authService.client
    .from('projects')
    .delete()
    .eq('project_id', projectId);
  if (error) throw error;
  cache.invalidate(`project:${projectId}`);
  cache.invalidatePrefix(`projects:${userId}`);
}

// ── Sessions ─────────────────────────────────────────────────

export async function loadProjectSessions(projectId) {
  const cacheKey = `sessions:${projectId}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const { data, error } = await authService.client
    .from('sessions')
    .select('session_id, title, updated_at, llm_model')
    .eq('project_id', projectId)
    .order('updated_at', { ascending: false });

  if (error) throw error;
  cache.set(cacheKey, data, TTL.sessions);
  return data;
}

export async function loadSessionHistory(sessionId) {
  const { data: events, error: e1 } = await authService.client
    .from('session_events')
    .select('*')
    .eq('session_id', sessionId)
    .order('order', { ascending: true });
  if (e1) throw e1;

  const { data: attachments, error: e2 } = await authService.client
    .from('session_attachments')
    .select('*')
    .eq('session_id', sessionId);
  if (e2) throw e2;

  const { data: session, error: e3 } = await authService.client
    .from('sessions')
    .select('*')
    .eq('session_id', sessionId)
    .single();
  if (e3) throw e3;

  return { events: events ?? [], attachments: attachments ?? [], session };
}

export async function createSession(projectId, userId, title = null, llmModel = 'gemini-2.5-flash') {
  const { data, error } = await authService.client
    .from('sessions')
    .insert({ project_id: projectId, user_id: userId, title, llm_model: llmModel })
    .select('session_id, title, llm_model')
    .single();
  if (error) throw error;
  cache.invalidate(`sessions:${projectId}`);
  return data;
}

export async function deleteSession(sessionId, projectId) {
  const { error } = await authService.client
    .from('sessions')
    .delete()
    .eq('session_id', sessionId);
  if (error) throw error;
  cache.invalidate(`sessions:${projectId}`);
}

// ── User Details ─────────────────────────────────────────────

export async function loadUserDetails(userId) {
  const cacheKey = `user:${userId}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const { data, error } = await authService.client
    .from('user_details')
    .select('*')
    .eq('user_id', userId)
    .maybeSingle();

  if (error) throw error;
  cache.set(cacheKey, data, TTL.userDetails);
  return data;
}

export async function upsertUserDetails(details) {
  const { error } = await authService.client
    .from('user_details')
    .upsert(details, { onConflict: 'user_id' });
  if (error) throw error;
  cache.invalidate(`user:${details.user_id}`);
}

// ── Company Details ──────────────────────────────────────────

export async function loadCompanyDetails(companyId) {
  const cacheKey = `company:${companyId}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const { data, error } = await authService.client
    .from('company_details')
    .select('*')
    .eq('company_id', companyId)
    .maybeSingle();

  if (error) throw error;
  cache.set(cacheKey, data, TTL.company);
  return data;
}

export async function upsertCompanyDetails(details) {
  const { error } = await authService.client
    .from('company_details')
    .upsert(details, { onConflict: 'company_id' });
  if (error) throw error;
  cache.invalidate(`company:${details.company_id}`);
}

export async function loadAllCompanies() {
  const { data, error } = await authService.client
    .from('company_details')
    .select('*');
  if (error) throw error;
  return data ?? [];
}

// ── Agent Chat (SSE streaming) ───────────────────────────────

/**
 * Stream a chat message to the FastAPI backend.
 * Mirrors streaming_service.py stream_response()
 *
 * @param {object} request - AskAgentRequest shape
 * @param {object} callbacks - { onToken, onAiMessage, onToolResult, onReasoning, onDone, onError }
 * @returns {AbortController} - call .abort() to cancel
 */
export function streamChat(request, callbacks = {}) {
  const controller = new AbortController();

  (async () => {
    try {
      const token = await authService.getAccessToken();
      const res = await fetch(`${CONFIG.backendUrl}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type':  'application/json',
          'Authorization': `Bearer ${token}`,
          'Accept':        'text/event-stream',
        },
        body: JSON.stringify(request),
        signal: controller.signal,
      });

      if (!res.ok) {
        const msg = await res.text();
        callbacks.onError?.(new Error(`${res.status}: ${msg}`));
        return;
      }

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let   buffer  = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete line

        for (const line of lines) {
          if (!line.startsWith('data:')) continue;
          const raw = line.slice(5).trim();
          if (!raw) continue;

          let data;
          try { data = JSON.parse(raw); } catch { continue; }

          // Unwrap list wrapper (backward compat)
          if (Array.isArray(data) && data.length === 1) data = data[0];
          if (typeof data !== 'object') continue;

          const type = data.type;
          if (type === 'token')       callbacks.onToken?.(data.data, data.query_id);
          else if (type === 'reasoning')   callbacks.onReasoning?.(data.data);
          else if (type === 'ai_message')  callbacks.onAiMessage?.(data);
          else if (type === 'tool_result') callbacks.onToolResult?.(data);
          else if (type === 'error')       callbacks.onError?.(new Error(data.data));
        }
      }

      callbacks.onDone?.();
    } catch (err) {
      if (err.name !== 'AbortError') callbacks.onError?.(err);
    }
  })();

  return controller;
}

// ── Project pipeline (SSE streaming) ────────────────────────

export function streamProjectInit(request, callbacks = {}) {
  return _streamProject('/project/init-project', request, callbacks);
}

export function streamProjectUpdate(request, callbacks = {}) {
  return _streamProject('/project/update-project', request, callbacks);
}

function _streamProject(path, request, callbacks) {
  const controller = new AbortController();

  (async () => {
    try {
      const token = await authService.getAccessToken();
      const res = await fetch(`${CONFIG.backendUrl}${path}`, {
        method: 'POST',
        headers: {
          'Content-Type':  'application/json',
          'Authorization': `Bearer ${token}`,
          'Accept':        'text/event-stream',
        },
        body: JSON.stringify(request),
        signal: controller.signal,
      });

      if (!res.ok) throw new Error(`${res.status}`);

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let   buffer  = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith('data:')) continue;
          const raw = line.slice(5).trim();
          if (!raw) continue;
          let data;
          try { data = JSON.parse(raw); } catch { continue; }
          callbacks.onChunk?.(data);
        }
      }
      callbacks.onDone?.();
    } catch (err) {
      if (err.name !== 'AbortError') callbacks.onError?.(err);
    }
  })();

  return controller;
}
