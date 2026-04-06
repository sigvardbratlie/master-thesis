// ============================================================
// PROJECT DASHBOARD — single project view
// Layout ref:  new-ui/project_dashboard.html
// Logic ref:   ui/src/ui/ui_components/chat_component.py
//              ui/src/ui/ui_components/project_component.py
//              ui/src/ui/services/streaming_service.py
// ============================================================

import {
  loadProject, loadProjectSessions, loadSessionHistory,
  createSession, deleteSession, streamChat,
} from '../api.js';
import { renderSidebar, bindSidebarEvents } from '../components/sidebar.js';
import { renderTopbar }                     from '../components/topbar.js';
import { appState }                         from '../state.js';
import { formatDate, timeAgo, toast, skeleton, uuid, escHtml } from '../utils.js';
import { marked }                           from 'marked';
import { chatLog }                          from '../logger.js';

// Configure marked: safe, breaks on newline
marked.setOptions({ breaks: true, gfm: true });
const md = (text) => marked.parse(text ?? '');

// ── Active streaming controller (cancel on navigation) ──────
let _streamController = null;

export async function renderProject(params) {
  const projectId = params.id;

  document.getElementById('app').innerHTML = `
    ${renderSidebar()}
    <div class="ml-64 min-h-screen bg-surface flex flex-col">
      ${renderTopbar({
        title: 'Loading...',
        breadcrumb: { label: 'Projects', href: '#/' },
      })}
      <div id="project-body" class="flex-1 flex">
        <div class="flex-1 p-10 space-y-4">${skeleton(5)}</div>
      </div>
    </div>`;

  bindSidebarEvents();

  try {
    const [data, sessions] = await Promise.all([
      loadProject(projectId),
      loadProjectSessions(projectId),
    ]);
    buildProjectShell(projectId, data, sessions);
  } catch (err) {
    document.getElementById('project-body').innerHTML =
      `<div class="p-10 text-error text-sm">${err.message}</div>`;
  }
}

// ── Shell layout ─────────────────────────────────────────────

function buildProjectShell(projectId, data, sessions) {
  const { factsheet, attachments, emails } = data;
  const title = factsheet.title ?? 'Untitled Project';

  // Update topbar title
  document.querySelector('#app header h2').textContent = title;

  document.getElementById('project-body').innerHTML = `
    <!-- Left: factsheet + timeline (scrollable) -->
    <div class="flex-1 overflow-y-auto p-10 space-y-12 min-w-0" id="factsheet-panel">
      ${buildTimeline(factsheet.events ?? [])}
      ${buildPartiesSection(factsheet.parties ?? [])}
      ${buildFactsheetGrid(factsheet, attachments, emails)}
    </div>

    <!-- Drag handle -->
    <div id="chat-resize-handle"
      class="w-1 flex-shrink-0 cursor-col-resize bg-outline-variant/10 hover:bg-secondary/30 active:bg-secondary/50 transition-colors relative group"
      title="Drag to resize">
      <div class="absolute inset-y-0 -left-1 -right-1"></div>
    </div>

    <!-- Right: chat panel -->
    <div class="flex-shrink-0 border-l border-outline-variant/10 bg-surface-container-low flex flex-col" id="chat-panel" style="width:400px; min-width:280px; max-width:700px">
      ${buildChatPanel(projectId, sessions)}
    </div>`;

  bindProjectEvents(projectId, data, sessions);
  bindChatResize();
}

// ── Timeline ─────────────────────────────────────────────────

function buildTimeline(events) {
  const items = events.length
    ? events.slice(0, 6).map((ev, i) => timelineItem(ev, i)).join('')
    : `<p class="text-on-surface-variant text-sm font-body py-6">No events recorded yet. Ask the agent to extract case events.</p>`;

  return `
    <section>
      <div class="flex items-end justify-between mb-5">
        <div>
          <h3 class="font-headline font-black text-2xl text-primary tracking-tight">Case Chronology</h3>
          <p class="text-on-surface-variant text-sm font-body mt-1">Key events and documentation milestones</p>
        </div>
        <div class="flex gap-2">
          <button class="px-4 py-1.5 text-xs font-bold uppercase tracking-wider bg-surface-container text-secondary rounded-full hover:bg-surface-container-high transition-colors">
            Export
          </button>
        </div>
      </div>
      <div class="relative overflow-x-auto pb-6 pt-4">
        <div class="min-w-[800px] relative px-4">
          <div class="absolute top-1/2 left-0 w-full h-[2px] bg-secondary/15 -translate-y-1/2 pointer-events-none"></div>
          <div class="flex justify-between relative gap-4">
            ${items}
          </div>
        </div>
      </div>
    </section>`;
}

function timelineItem(ev, i) {
  const isAbove = i % 2 === 0;
  const isKey   = ev.is_key_event;
  const dot     = isKey
    ? `<div class="w-5 h-5 bg-primary rounded-full ring-[5px] ring-secondary-container/30 z-10 flex-shrink-0"></div>`
    : `<div class="w-3.5 h-3.5 bg-secondary rounded-full ring-4 ring-surface z-10 flex-shrink-0"></div>`;
  const card = `
    <div class="p-4 bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10 shadow-sm w-44
                ${isKey ? 'ring-secondary/20 shadow-lg' : ''}
                transition-all hover:-translate-y-0.5 hover:shadow-md">
      <span class="text-[9px] font-bold text-secondary uppercase block mb-1">${formatDate(ev.date ?? ev.event_date, { day: 'numeric', month: 'short', year: 'numeric' })}</span>
      <p class="text-xs font-semibold text-primary leading-tight line-clamp-3">${escHtml(ev.description ?? ev.event_description ?? '')}</p>
    </div>`;

  return isAbove
    ? `<div class="relative flex flex-col items-center group">${card}${dot}</div>`
    : `<div class="relative flex flex-col items-center group">${dot}${card}</div>`;
}

// ── Parties ───────────────────────────────────────────────────

function buildPartiesSection(parties) {
  if (!parties.length) return '';

  const cards = parties.map(p => {
    const initial = (p.party_name ?? p.name ?? '?')[0].toUpperCase();
    const role    = p.party_role ?? p.role ?? '';
    const name    = p.party_name ?? p.name ?? 'Unknown';
    return `
      <div class="flex items-center gap-3 p-3 bg-surface-container-lowest rounded-xl
                  ring-1 ring-transparent hover:ring-secondary/20 transition-all group">
        <div class="w-10 h-10 rounded-lg bg-primary-container flex items-center justify-center flex-shrink-0">
          <span class="text-on-primary text-sm font-bold">${initial}</span>
        </div>
        <div class="min-w-0">
          <h4 class="text-sm font-bold text-on-surface truncate">${escHtml(name)}</h4>
          <p class="text-[10px] font-bold text-secondary uppercase tracking-tight">${escHtml(role)}</p>
        </div>
        <button class="ml-auto p-1.5 rounded hover:bg-surface-container transition-colors opacity-0 group-hover:opacity-100">
          <span class="material-symbols-outlined text-[16px]">mail</span>
        </button>
      </div>`;
  });

  return `
    <section class="grid grid-cols-1 lg:grid-cols-12 gap-10">
      <div class="lg:col-span-5">
        <h3 class="font-headline font-bold text-lg text-primary mb-1">Active Parties</h3>
        <p class="text-on-surface-variant text-xs mb-5">Identified legal entities and witnesses</p>
        <div class="bg-surface-container rounded-2xl p-5 space-y-2">
          ${cards.join('')}
        </div>
      </div>
      <div class="lg:col-span-7" id="claims-damages-section">
        ${buildClaimsDamages([])}
      </div>
    </section>`;
}

function buildClaimsDamages(claims) {
  if (!claims.length) return '';
  return `
    <h3 class="font-headline font-bold text-lg text-primary mb-1">Claims</h3>
    <p class="text-on-surface-variant text-xs mb-5">Legal claims and requested relief</p>
    <div class="space-y-3">
      ${claims.map(c => `
        <div class="p-4 bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10">
          <p class="text-sm font-semibold text-on-surface">${escHtml(c.claim_description ?? c.description ?? '')}</p>
          ${c.amount ? `<p class="text-xs font-bold text-secondary mt-1">${c.amount}</p>` : ''}
        </div>`).join('')}
    </div>`;
}

// ── Factsheet grid ───────────────────────────────────────────

function buildFactsheetGrid(factsheet, attachments, emails) {
  const deadlines = factsheet.deadlines ?? [];
  const damages   = factsheet.damages   ?? [];

  return `
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">

      <!-- Deadlines -->
      <section>
        <h3 class="font-headline font-bold text-lg text-primary mb-4">Deadlines</h3>
        <div class="space-y-2">
          ${deadlines.length
            ? deadlines.map(d => `
              <div class="flex items-center justify-between p-3.5 bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10">
                <div>
                  <p class="text-sm font-semibold text-on-surface">${escHtml(d.description ?? d.deadline_description ?? '')}</p>
                  <p class="text-[10px] text-on-surface-variant mt-0.5">${formatDate(d.date ?? d.deadline_date)}</p>
                </div>
                <span class="material-symbols-outlined text-[18px] text-tertiary-fixed-dim">event</span>
              </div>`).join('')
            : `<p class="text-on-surface-variant text-sm font-body py-4">No deadlines recorded.</p>`
          }
        </div>
      </section>

      <!-- Damages -->
      <section>
        <h3 class="font-headline font-bold text-lg text-primary mb-4">Damages</h3>
        <div class="space-y-2">
          ${damages.length
            ? damages.map(d => `
              <div class="flex items-center justify-between p-3.5 bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10">
                <p class="text-sm font-semibold text-on-surface">${escHtml(d.description ?? d.damage_description ?? '')}</p>
                ${d.amount ? `<span class="text-sm font-bold text-secondary flex-shrink-0 ml-4">${escHtml(String(d.amount))}</span>` : ''}
              </div>`).join('')
            : `<p class="text-on-surface-variant text-sm font-body py-4">No damages recorded.</p>`
          }
        </div>
      </section>

      <!-- Attachments -->
      <section class="lg:col-span-2">
        <div class="flex items-center justify-between mb-4">
          <h3 class="font-headline font-bold text-lg text-primary">Documents</h3>
          <div class="flex gap-2">
            <span class="px-2.5 py-1 rounded-full bg-secondary-container/30 text-on-secondary-container text-xs font-bold">
              ${attachments.length} files
            </span>
            <span class="px-2.5 py-1 rounded-full bg-surface-container text-on-surface-variant text-xs font-bold">
              ${emails.length} emails
            </span>
          </div>
        </div>
        ${buildAttachmentsList(attachments, emails)}
      </section>
    </div>`;
}

function buildAttachmentsList(attachments, emails) {
  const fileIconMap = {
    'application/pdf': 'picture_as_pdf',
    'message/rfc822':  'mail',
    'default':         'description',
  };

  const attItems = attachments.slice(0, 8).map(a => `
    <div class="flex items-center gap-3 p-3 bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10 hover:ring-secondary/20 transition-all group cursor-pointer">
      <span class="material-symbols-outlined text-[20px] text-secondary">
        ${fileIconMap[a.file_type] ?? fileIconMap.default}
      </span>
      <div class="flex-1 min-w-0">
        <p class="text-xs font-semibold text-on-surface truncate">${escHtml(a.filename ?? '')}</p>
        <p class="text-[10px] text-on-surface-variant">${formatDate(a.file_date ?? a.created_at)}</p>
      </div>
    </div>`);

  const emailItems = emails.slice(0, 4).map(e => `
    <div class="flex items-center gap-3 p-3 bg-surface-container-lowest rounded-xl ring-1 ring-outline-variant/10 hover:ring-secondary/20 transition-all group cursor-pointer">
      <span class="material-symbols-outlined text-[20px] text-on-surface-variant">mail</span>
      <div class="flex-1 min-w-0">
        <p class="text-xs font-semibold text-on-surface truncate">${escHtml(e.subject ?? 'No subject')}</p>
        <p class="text-[10px] text-on-surface-variant">${escHtml(e.from_addr ?? '')} · ${formatDate(e.date)}</p>
      </div>
    </div>`);

  if (!attItems.length && !emailItems.length) {
    return `<p class="text-on-surface-variant text-sm font-body py-2">No documents attached.</p>`;
  }

  return `<div class="grid grid-cols-2 gap-2">${[...attItems, ...emailItems].join('')}</div>`;
}

// ── Chat panel ────────────────────────────────────────────────

function buildChatPanel(projectId, sessions) {
  const sessionOptions = sessions.map(s =>
    `<option value="${s.session_id}">${escHtml(s.title ?? 'Untitled Session')}</option>`
  ).join('');

  return `
    <!-- Session selector -->
    <div class="p-4 border-b border-outline-variant/10 flex items-center gap-2">
      <span class="material-symbols-outlined text-[18px] text-on-surface-variant">chat</span>
      <select id="session-select"
        class="flex-1 bg-transparent text-sm font-semibold text-on-surface outline-none cursor-pointer">
        <option value="">— New session —</option>
        ${sessionOptions}
      </select>
      <button id="btn-new-session" title="New session"
        class="p-1.5 rounded-lg hover:bg-surface-container transition-colors">
        <span class="material-symbols-outlined text-[18px] text-on-surface-variant">add</span>
      </button>
      <button id="btn-delete-session" title="Delete session"
        class="p-1.5 rounded-lg hover:bg-error-container/40 transition-colors">
        <span class="material-symbols-outlined text-[18px] text-on-surface-variant hover:text-error">delete</span>
      </button>
    </div>

    <!-- Messages -->
    <div id="chat-messages" class="flex-1 overflow-y-auto p-4 space-y-4 font-body text-sm">
      <div id="chat-welcome" class="flex flex-col items-center justify-center h-full py-12 text-center">
        <span class="material-symbols-outlined text-4xl text-on-surface-variant/30 mb-3">chat_bubble</span>
        <p class="text-on-surface-variant text-sm">Select a session or start a new conversation.</p>
      </div>
    </div>

    <!-- Input area -->
    <div class="p-4 border-t border-outline-variant/10">
      <!-- Model selector -->
      <div class="flex items-center gap-2 mb-3">
        <span class="material-symbols-outlined text-[14px] text-on-surface-variant">smart_toy</span>
        <select id="model-select" class="text-xs text-on-surface-variant bg-transparent outline-none cursor-pointer">
          <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
          <option value="gemini-2.5-pro">Gemini 2.5 Pro</option>
          <option value="gpt-4o-mini">GPT-4o Mini</option>
        </select>
      </div>

      <!-- Text input -->
      <div class="flex items-end gap-2">
        <textarea
          id="chat-input"
          rows="2"
          placeholder="Ask a question about this case..."
          class="flex-1 resize-none bg-surface-container ring-1 ring-outline-variant/20 focus:ring-2 focus:ring-secondary
                 rounded-xl px-3.5 py-2.5 text-sm font-body outline-none transition-all placeholder:text-on-surface-variant/40"
        ></textarea>
        <button id="btn-send"
          class="flex-shrink-0 p-2.5 rounded-xl bg-gradient-to-b from-primary to-primary-container text-on-primary
                 hover:opacity-90 transition-opacity disabled:opacity-40">
          <span class="material-symbols-outlined text-[20px]">send</span>
        </button>
      </div>

      <!-- File upload -->
      <div class="mt-2 flex items-center gap-2">
        <label for="file-upload" class="flex items-center gap-1.5 cursor-pointer text-xs text-on-surface-variant hover:text-secondary transition-colors">
          <span class="material-symbols-outlined text-[16px]">attach_file</span>
          Attach file
        </label>
        <input id="file-upload" type="file" class="hidden" multiple
               accept=".pdf,.txt,.eml,.csv,.xlsx,.pptx,.docx">
        <div id="file-chips" class="flex flex-wrap gap-1"></div>
      </div>
    </div>`;
}

// ── Chat state ────────────────────────────────────────────────

const chatState = {
  projectId:  null,
  sessionId:  null,
  messages:   [],       // { role, content, type, queryId }
  pendingFiles: [],     // File objects
  streaming:  false,
};

function bindProjectEvents(projectId, data, sessions) {
  chatState.projectId = projectId;
  chatState.sessions  = sessions;

  // Session selector
  document.getElementById('session-select')?.addEventListener('change', async (e) => {
    const sid = e.target.value;
    if (!sid) {
      chatState.sessionId = null;
      chatState.messages  = [];
      renderMessages();
      return;
    }
    chatState.sessionId = sid;
    await loadSession(sid);
  });

  // New session button
  document.getElementById('btn-new-session')?.addEventListener('click', async () => {
    await startNewSession(projectId);
  });

  // Delete session button
  document.getElementById('btn-delete-session')?.addEventListener('click', async () => {
    if (!chatState.sessionId) return;
    if (!confirm('Delete this session?')) return;
    try {
      await deleteSession(chatState.sessionId, projectId);
      chatState.sessionId = null;
      chatState.messages  = [];
      toast('Session deleted', 'success');
      // Refresh sessions list
      const updated = await loadProjectSessions(projectId);
      updateSessionSelect(updated);
      renderMessages();
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  // Send button
  document.getElementById('btn-send')?.addEventListener('click', () => sendMessage(projectId));

  // Enter key (Shift+Enter for newline)
  document.getElementById('chat-input')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(projectId);
    }
  });

  // File upload
  document.getElementById('file-upload')?.addEventListener('change', (e) => {
    chatState.pendingFiles = Array.from(e.target.files ?? []);
    renderFileChips();
  });
}

function updateSessionSelect(sessions) {
  const sel = document.getElementById('session-select');
  if (!sel) return;
  const opts = sessions.map(s =>
    `<option value="${s.session_id}" ${s.session_id === chatState.sessionId ? 'selected' : ''}>
      ${escHtml(s.title ?? 'Untitled Session')}
    </option>`
  ).join('');
  sel.innerHTML = `<option value="">— New session —</option>${opts}`;
}

async function startNewSession(projectId) {
  try {
    const session = await createSession(projectId, appState.user.id);
    chatState.sessionId = session.session_id;
    chatState.messages  = [];
    const updated = await loadProjectSessions(projectId);
    updateSessionSelect(updated);
    renderMessages();
    toast('New session started', 'success');
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function loadSession(sessionId) {
  const messagesEl = document.getElementById('chat-messages');
  if (messagesEl) messagesEl.innerHTML = `<div class="space-y-3">${skeleton(4)}</div>`;

  try {
    const { events } = await loadSessionHistory(sessionId);
    chatState.messages = events.map(ev => ({
      role:    ev.type,
      content: getEventContent(ev),
      type:    ev.type,
      queryId: ev.query_id,
      toolData: ev.type === 'tool_result' ? ev.data : null,
    }));
    renderMessages();
  } catch (err) {
    toast(err.message, 'error');
  }
}

function getEventContent(ev) {
  // ev.data kan være string (JSON), objekt, eller null
  let d = ev.data ?? {};
  if (typeof d === 'string') {
    try { d = JSON.parse(d); } catch { d = { content: d }; }
  }

  chatLog.debug({ type: ev.type, dataKeys: Object.keys(d) }, 'getEventContent');

  if (ev.type === 'human')       return d.content ?? '';
  if (ev.type === 'ai')          return d.token_stream ?? d.content ?? '';
  if (ev.type === 'tool_result') return d.tool_name ?? '';
  return '';
}

// ── Sending messages ─────────────────────────────────────────

async function sendMessage(projectId) {
  if (chatState.streaming) return;

  const inputEl  = document.getElementById('chat-input');
  const question = inputEl?.value.trim();
  if (!question) return;

  // Ensure session
  if (!chatState.sessionId) {
    await startNewSession(projectId);
    if (!chatState.sessionId) return;
  }

  inputEl.value = '';
  inputEl.disabled = true;
  document.getElementById('btn-send').disabled = true;

  const queryId = uuid();
  const model   = document.getElementById('model-select')?.value ?? 'gemini-2.5-flash';

  // Build file attachments (base64)
  const attachments = await buildAttachmentPayloads(chatState.pendingFiles, queryId);
  chatState.pendingFiles = [];
  renderFileChips();

  // Add human message to UI
  chatState.messages.push({ role: 'human', content: question, type: 'human', queryId });
  renderMessages();

  // Streaming AI message placeholder
  const aiMsg = { role: 'ai', content: '', type: 'ai', queryId, streaming: true };
  chatState.messages.push(aiMsg);
  chatState.streaming = true;
  renderMessages();

  const request = {
    question,
    attachments,
    session_id:  chatState.sessionId,
    llm_model:   model,
    query_id:    queryId,
    project_id:  projectId,
  };

  _streamController = streamChat(request, {
    onToken: (token) => {
      aiMsg.content += token;
      updateStreamingMessage(aiMsg);
    },
    onReasoning: (text) => {
      aiMsg.reasoning = (aiMsg.reasoning ?? '') + text;
      updateStreamingMessage(aiMsg);
    },
    onToolResult: (data) => {
      chatState.messages.push({ role: 'tool_result', content: `Tool: ${data.tool_name ?? ''}`, type: 'tool_result', toolData: data, queryId });
      renderMessages(true);
    },
    onDone: () => {
      aiMsg.streaming = false;
      chatState.streaming = false;
      inputEl.disabled = false;
      document.getElementById('btn-send').disabled = false;
      renderMessages();
    },
    onError: (err) => {
      aiMsg.content += `\n\n*Error: ${err.message}*`;
      aiMsg.streaming = false;
      chatState.streaming = false;
      inputEl.disabled = false;
      document.getElementById('btn-send').disabled = false;
      renderMessages();
      toast(err.message, 'error');
    },
  });
}

async function buildAttachmentPayloads(files, queryId) {
  return Promise.all(files.map(async (file) => {
    const bytes  = await file.arrayBuffer();
    const base64 = btoa(String.fromCharCode(...new Uint8Array(bytes)));
    const fileId = uuid();
    return {
      filename:  file.name,
      file_id:   fileId,
      content:   base64,
      path:      `${appState.user.id}/${chatState.sessionId}/${fileId}${file.name.slice(file.name.lastIndexOf('.'))}`,
      file_type: file.type,
      size:      file.size,
      query_id:  queryId,
    };
  }));
}

// ── Message rendering ─────────────────────────────────────────

function renderMessages(keepScroll = false) {
  const el = document.getElementById('chat-messages');
  if (!el) return;

  if (!chatState.messages.length) {
    el.innerHTML = `
      <div class="flex flex-col items-center justify-center h-full py-12 text-center">
        <span class="material-symbols-outlined text-4xl text-on-surface-variant/30 mb-3">chat_bubble</span>
        <p class="text-on-surface-variant text-sm">Ask a question to begin the conversation.</p>
      </div>`;
    return;
  }

  const wasAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
  el.innerHTML = chatState.messages.map(msg => renderMessage(msg)).join('');

  if (!keepScroll && (wasAtBottom || chatState.streaming)) {
    el.scrollTop = el.scrollHeight;
  }
}

function updateStreamingMessage(aiMsg) {
  const el = document.querySelector(`[data-query-id="${aiMsg.queryId}"].ai-message`);
  if (!el) { renderMessages(); return; }
  const contentEl = el.querySelector('.msg-content');
  if (contentEl) contentEl.innerHTML = md(aiMsg.content);
  const dotEl = el.querySelector('.streaming-dot');
  if (dotEl) dotEl.classList.toggle('hidden', !aiMsg.streaming);
  const messages = document.getElementById('chat-messages');
  if (messages) messages.scrollTop = messages.scrollHeight;
}

// ── Resize drag handle ────────────────────────────────────────

function bindChatResize() {
  const handle = document.getElementById('chat-resize-handle');
  const panel  = document.getElementById('chat-panel');
  if (!handle || !panel) return;

  let startX = 0, startW = 0;

  handle.addEventListener('mousedown', (e) => {
    startX = e.clientX;
    startW = panel.getBoundingClientRect().width;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    function onMove(e) {
      const delta = startX - e.clientX;        // drag left = wider chat
      const newW  = Math.min(700, Math.max(280, startW + delta));
      panel.style.width = `${newW}px`;
    }
    function onUp() {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    }
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });
}

function renderMessage(msg) {
  if (msg.type === 'human') {
    return `
      <div class="flex justify-end">
        <div class="max-w-[85%] bg-primary-container text-on-primary rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed">
          ${escHtml(msg.content)}
        </div>
      </div>`;
  }

  if (msg.type === 'tool_result') {
    const toolName = msg.content || msg.toolData?.tool_name ?? msg.toolData?.data?.tool_name ?? 'tool';
    return `
      <div class="flex items-start gap-2">
        <span class="material-symbols-outlined text-[16px] text-on-surface-variant mt-0.5 flex-shrink-0">build</span>
        <details class="flex-1 bg-surface-container rounded-xl overflow-hidden text-xs">
          <summary class="px-3 py-2 font-bold text-on-surface-variant cursor-pointer hover:bg-surface-container-high transition-colors list-none flex items-center gap-2">
            <span class="material-symbols-outlined text-[14px]">chevron_right</span>
            ${escHtml(toolName)}
          </summary>
          <div class="px-3 pb-3 text-on-surface-variant font-mono overflow-x-auto">
            <pre class="whitespace-pre-wrap text-[10px]">${escHtml(JSON.stringify(msg.toolData?.data ?? {}, null, 2))}</pre>
          </div>
        </details>
      </div>`;
  }

  // AI message
  return `
    <div class="flex items-start gap-2 ai-message" data-query-id="${msg.queryId ?? ''}">
      <div class="w-6 h-6 rounded-full bg-secondary-container flex items-center justify-center flex-shrink-0 mt-0.5">
        <span class="material-symbols-outlined text-[14px] text-secondary" style="font-variation-settings:'FILL' 1">smart_toy</span>
      </div>
      <div class="flex-1 min-w-0">
        ${msg.reasoning ? `
          <details class="mb-2 text-xs text-on-surface-variant">
            <summary class="cursor-pointer hover:text-primary transition-colors font-bold">Reasoning</summary>
            <div class="mt-1 font-body leading-relaxed opacity-70 prose prose-sm max-w-none">${md(msg.reasoning)}</div>
          </details>` : ''}
        <div class="msg-content prose prose-sm max-w-none text-on-surface font-body leading-relaxed
                    prose-headings:font-headline prose-headings:text-primary
                    prose-code:bg-surface-container prose-code:px-1 prose-code:rounded prose-code:text-xs
                    prose-pre:bg-surface-container prose-pre:rounded-xl prose-pre:text-xs">
          ${msg.content ? md(msg.content) : ''}
          <span class="streaming-dot ${msg.streaming ? '' : 'hidden'} inline-block w-1.5 h-3.5 bg-secondary animate-pulse rounded-sm ml-0.5 align-middle"></span>
        </div>
      </div>
    </div>`;
}

function renderFileChips() {
  const el = document.getElementById('file-chips');
  if (!el) return;
  el.innerHTML = chatState.pendingFiles.map((f, i) => `
    <div class="flex items-center gap-1 px-2 py-0.5 rounded-full bg-secondary-container/30 text-on-secondary-container text-[10px] font-semibold">
      ${escHtml(f.name.length > 20 ? f.name.slice(0,18) + '…' : f.name)}
      <button class="ml-1 hover:text-error" data-file-index="${i}">×</button>
    </div>`).join('');

  el.querySelectorAll('[data-file-index]').forEach(btn => {
    btn.addEventListener('click', () => {
      chatState.pendingFiles.splice(Number(btn.dataset.fileIndex), 1);
      renderFileChips();
    });
  });
}
