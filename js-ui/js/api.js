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
  projectMeta:   60_000,  // 1 min
  section:       60_000,  // 1 min (events, parties, claims, etc.)
  emailBody:     30_000,  // 30 s  (on-demand, cleared on reload)
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
    .select('project_id, title, background, created_at, project_parties(legal_name, role)')
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

// ── Per-table project loaders ────────────────────────────────

export async function loadProjectMeta(projectId) {
  const cacheKey = `project-meta:${projectId}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const { data, error } = await authService.client
    .from('projects')
    .select('project_id, title, background, created_at, start_date')
    .eq('project_id', projectId)
    .single();

  if (error) throw error;
  cache.set(cacheKey, data, TTL.projectMeta);
  return data;
}

export async function loadProjectEvents(projectId) {
  const cacheKey = `project-events:${projectId}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const { data, error } = await authService.client
    .from('project_events')
    .select('event_id, event_name, description, significance, category, event_start_date, event_end_date, disputed, parties, email_id, file_id, project_id, created_by, updated_by, created_at, updated_at')
    .eq('project_id', projectId)
    .order('event_start_date', { ascending: true });

  if (error) throw error;
  cache.set(cacheKey, data ?? [], TTL.section);
  return data ?? [];
}

export async function loadProjectParties(projectId) {
  const cacheKey = `project-parties:${projectId}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const { data, error } = await authService.client
    .from('project_parties')
    .select('*, project_party_reps(*)')
    .eq('project_id', projectId);

  if (error) throw error;
  cache.set(cacheKey, data ?? [], TTL.section);
  return data ?? [];
}

export async function loadProjectClaims(projectId) {
  const cacheKey = `project-claims:${projectId}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const { data, error } = await authService.client
    .from('project_claims')
    .select('claim_id, title, factual_basis, legal_basis, defense, party_role, relief_sought, strength_assessment, category, significance, email_id, file_id, project_id, created_by, updated_by, created_at, updated_at')
    .eq('project_id', projectId);

  if (error) throw error;
  cache.set(cacheKey, data ?? [], TTL.section);
  return data ?? [];
}

export async function loadProjectDeadlines(projectId) {
  const cacheKey = `project-deadlines:${projectId}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const { data, error } = await authService.client
    .from('project_deadlines')
    .select('deadline_id, title, description, deadline_date, party_role, significance, email_id, file_id, project_id, created_by, updated_by, created_at, updated_at')
    .eq('project_id', projectId)
    .order('deadline_date', { ascending: true });

  if (error) throw error;
  cache.set(cacheKey, data ?? [], TTL.section);
  return data ?? [];
}

export async function loadProjectDamages(projectId) {
  const cacheKey = `project-damages:${projectId}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const { data, error } = await authService.client
    .from('project_damages')
    .select('damage_id, title, basis, category, amount, currency, party_role, significance, supporting_evidence, email_id, file_id, project_id, created_by, updated_by, created_at, updated_at')
    .eq('project_id', projectId);

  if (error) throw error;
  cache.set(cacheKey, data ?? [], TTL.section);
  return data ?? [];
}

export async function loadProjectAttachments(projectId) {
  const cacheKey = `project-attachments:${projectId}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const { data, error } = await authService.client
    .from('project_attachments')
    .select('file_id, filename, file_type, path, file_date, created_at, category, significance')
    .eq('project_id', projectId)
    .order('created_at', { ascending: false });

  if (error) throw error;
  cache.set(cacheKey, data ?? [], TTL.section);
  return data ?? [];
}

export async function loadProjectEmails(projectId) {
  const cacheKey = `project-emails:${projectId}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  // Intentionally excludes `body` — fetched on-demand via loadEmailBody
  const { data, error } = await authService.client
    .from('project_emails')
    .select('email_id, from_addr, to, cc, subject, date, message_id, significance')
    .eq('project_id', projectId)
    .order('date', { ascending: false });

  if (error) throw error;
  cache.set(cacheKey, data ?? [], TTL.section);
  return data ?? [];
}

export async function loadEmailBody(emailId) {
  const cacheKey = `email-body:${emailId}`;
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const { data, error } = await authService.client
    .from('project_emails')
    .select('body')
    .eq('email_id', emailId)
    .maybeSingle();

  if (error) throw error;
  const body = data?.body ?? '';
  cache.set(cacheKey, body, TTL.emailBody);
  return body;
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
  // Fetch file_ids before deleting from Supabase (cascade will remove them)
  const { data: attachments } = await authService.client
    .from('project_attachments')
    .select('file_id')
    .eq('project_id', projectId);
  const { data: emails } = await authService.client
    .from('project_emails')
    .select('email_id')
    .eq('project_id', projectId);

  const fileIds = [
    ...(attachments ?? []).map(a => a.file_id),
    ...(emails ?? []).map(e => e.email_id),
  ];

  // Clean up GCS storage and vectorstore in parallel (best-effort, don't block on failure)
  await Promise.allSettled([
    fileIds.length > 0
      ? apiFetch('/storage/delete-files', { method: 'DELETE', body: JSON.stringify({ file_ids: fileIds }) })
      : Promise.resolve(),
    apiFetch(`/vectorstore/delete-project/${projectId}`, { method: 'DELETE' }),
  ]);

  // Delete from Supabase (cascades to all child tables)
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

export function streamProjectCleanElements(request, callbacks = {}) {
  return _streamProject('/project/clean-project-elements', request, callbacks);
}

export function streamProjectCleanMetadata(request, callbacks = {}) {
  return _streamProject('/project/clean-metadata', request, callbacks);
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
          if (Array.isArray(data) && data.length === 1) data = data[0];
          if (typeof data !== 'object' || data === null) continue;

          // Backend error envelope: { error: "..." }
          if (data.error && !data.type) {
            callbacks.onError?.(new Error(data.error));
            continue;
          }

          const type = data.type;
          if (type === 'token') {
            callbacks.onToken?.(data.data, data.query_id);
          } else if (type === 'tool_result') {
            callbacks.onToolResult?.(data);
          } else if (type === 'error') {
            callbacks.onError?.(new Error(data.data ?? data.error));
          } else if (type === 'status') {
            callbacks.onChunk?.(data);
          } else {
            // Pass through any other structured data
            callbacks.onChunk?.(data);
          }
        }
      }
      callbacks.onDone?.();
    } catch (err) {
      if (err.name !== 'AbortError') callbacks.onError?.(err);
    }
  })();

  return controller;
}

// ── Entity update functions ──────────────────────────────────

function _withAudit(updates, userId) {
  return { ...updates, updated_at: new Date().toISOString(), updated_by: userId };
}

export async function updateProjectEvent(eventId, projectId, updates, userId) {
  const { data, error } = await authService.client
    .from('project_events')
    .update(_withAudit(updates, userId))
    .eq('event_id', eventId)
    .select()
    .single();
  if (error) throw error;
  if (projectId) cache.invalidate(`project-events:${projectId}`);
  return data;
}

export async function updateProjectClaim(claimId, projectId, updates, userId) {
  const { data, error } = await authService.client
    .from('project_claims')
    .update(_withAudit(updates, userId))
    .eq('claim_id', claimId)
    .select()
    .single();
  if (error) throw error;
  if (projectId) cache.invalidate(`project-claims:${projectId}`);
  return data;
}

export async function updateProjectDeadline(deadlineId, projectId, updates, userId) {
  const { data, error } = await authService.client
    .from('project_deadlines')
    .update(_withAudit(updates, userId))
    .eq('deadline_id', deadlineId)
    .select()
    .single();
  if (error) throw error;
  if (projectId) cache.invalidate(`project-deadlines:${projectId}`);
  return data;
}

export async function updateProjectDamage(damageId, projectId, updates, userId) {
  const { data, error } = await authService.client
    .from('project_damages')
    .update(_withAudit(updates, userId))
    .eq('damage_id', damageId)
    .select()
    .single();
  if (error) throw error;
  if (projectId) cache.invalidate(`project-damages:${projectId}`);
  return data;
}

export async function updateProjectParty(partyId, projectId, updates, userId) {
  const { data, error } = await authService.client
    .from('project_parties')
    .update(_withAudit(updates, userId))
    .eq('party_id', partyId)
    .select()
    .single();
  if (error) throw error;
  if (projectId) cache.invalidate(`project-parties:${projectId}`);
  return data;
}

// ── Entity delete functions ──────────────────────────────────

export async function deleteProjectEvent(eventId, projectId) {
  const { error } = await authService.client.from('project_events').delete().eq('event_id', eventId);
  if (error) throw error;
  if (projectId) cache.invalidate(`project-events:${projectId}`);
}

export async function deleteProjectParty(partyId, projectId) {
  // Remove representatives first to avoid FK violation
  await authService.client.from('project_party_reps').delete().eq('party_id', partyId);
  const { error } = await authService.client.from('project_parties').delete().eq('party_id', partyId);
  if (error) throw error;
  if (projectId) cache.invalidate(`project-parties:${projectId}`);
}

export async function deleteProjectClaim(claimId, projectId) {
  const { error } = await authService.client.from('project_claims').delete().eq('claim_id', claimId);
  if (error) throw error;
  if (projectId) cache.invalidate(`project-claims:${projectId}`);
}

export async function deleteProjectDeadline(deadlineId, projectId) {
  const { error } = await authService.client.from('project_deadlines').delete().eq('deadline_id', deadlineId);
  if (error) throw error;
  if (projectId) cache.invalidate(`project-deadlines:${projectId}`);
}

export async function deleteProjectDamage(damageId, projectId) {
  const { error } = await authService.client.from('project_damages').delete().eq('damage_id', damageId);
  if (error) throw error;
  if (projectId) cache.invalidate(`project-damages:${projectId}`);
}

// ── Entity insert functions ──────────────────────────────────

export async function insertProjectParty(projectId, userId, data) {
  const { data: result, error } = await authService.client
    .from('project_parties')
    .insert({ project_id: projectId, created_by: userId, ...data })
    .select('*').single();
  if (error) throw error;
  cache.invalidate(`project-parties:${projectId}`);
  return result;
}

export async function insertProjectPartyRep(projectId, partyId, userId, data) {
  const { data: result, error } = await authService.client
    .from('project_party_reps')
    .insert({
      project_id: projectId,
      party_id: partyId,
      created_by: userId,
      ...data,
    })
    .select('*')
    .single();
  if (error) throw error;
  if (projectId) cache.invalidate(`project-parties:${projectId}`);
  return result;
}

export async function updateProjectPartyRep(repId, projectId, updates, userId) {
  const { data: result, error } = await authService.client
    .from('project_party_reps')
    .update(_withAudit(updates, userId))
    .eq('party_rep_id', repId)
    .select('*')
    .single();
  if (error) throw error;
  if (projectId) cache.invalidate(`project-parties:${projectId}`);
  return result;
}

export async function deleteProjectPartyRep(repId, projectId) {
  const { error } = await authService.client
    .from('project_party_reps')
    .delete()
    .eq('party_rep_id', repId);
  if (error) throw error;
  if (projectId) cache.invalidate(`project-parties:${projectId}`);
}

export async function insertProjectDeadline(projectId, userId, data) {
  const { data: result, error } = await authService.client
    .from('project_deadlines')
    .insert({ project_id: projectId, created_by: userId, ...data })
    .select('*').single();
  if (error) throw error;
  cache.invalidate(`project-deadlines:${projectId}`);
  return result;
}

export async function insertProjectEvent(projectId, userId, data) {
  const { data: result, error } = await authService.client
    .from('project_events')
    .insert({ project_id: projectId, created_by: userId, ...data })
    .select('*').single();
  if (error) throw error;
  cache.invalidate(`project-events:${projectId}`);
  return result;
}

export async function insertProjectClaim(projectId, userId, data) {
  const { data: result, error } = await authService.client
    .from('project_claims')
    .insert({ project_id: projectId, created_by: userId, ...data })
    .select('*').single();
  if (error) throw error;
  cache.invalidate(`project-claims:${projectId}`);
  return result;
}

export async function insertProjectDamage(projectId, userId, data) {
  const { data: result, error } = await authService.client
    .from('project_damages')
    .insert({ project_id: projectId, created_by: userId, ...data })
    .select('*').single();
  if (error) throw error;
  cache.invalidate(`project-damages:${projectId}`);
  return result;
}
