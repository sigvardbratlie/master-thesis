// ============================================================
// CHAT PAGE — standalone chat workspace with project selector
// ============================================================

import {
  loadProjects, loadProjectSessions, loadSessionHistory,
  createSession, deleteSession, streamChat,
} from '../api.js';
import { renderSidebar, bindSidebarEvents } from '../components/sidebar.js';
import { renderTopbar }                     from '../components/topbar.js';
import { appState }                         from '../state.js';
import { formatDate, timeAgo, toast, skeleton, uuid, escHtml } from '../utils.js';
import { marked }                           from 'marked';
import { chatLog }                          from '../logger.js';

marked.setOptions({ breaks: true, gfm: true });
const md = (text) => marked.parse(text ?? '');

let _streamController = null;

const chatState = {
  projectId:    null,
  projectTitle: '',
  sessionId:    null,
  messages:     [],
  pendingFiles: [],
  streaming:    false,
};

// ── Entry point ───────────────────────────────────────────────

export async function renderChat(params = {}) {
  document.getElementById('app').innerHTML = `
    ${renderSidebar()}
    <div class="ml-64 h-screen bg-surface flex flex-col overflow-hidden">
      ${renderTopbar({ title: 'Chat' })}
      <div class="flex-1 flex min-h-0 overflow-hidden">

        <!-- Left panel: project + session selector -->
        <div class="w-72 flex-shrink-0 border-r border-outline-variant/10 bg-surface-container-low flex flex-col overflow-hidden">
          <div class="p-4 border-b border-outline-variant/10 flex-shrink-0">
            <p class="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant mb-2">Project</p>
            <select id="project-select"
              class="w-full bg-surface-container ring-1 ring-outline-variant/20 rounded-lg px-3 py-2 text-sm font-body outline-none cursor-pointer text-on-surface">
              <option value="">— Select a project —</option>
            </select>
          </div>

          <div class="flex-1 overflow-y-auto">
            <div class="p-4 border-b border-outline-variant/10 flex items-center justify-between">
              <p class="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">Sessions</p>
              <button id="btn-new-session"
                class="flex items-center gap-1 text-xs text-secondary hover:text-primary font-semibold transition-colors disabled:opacity-40"
                disabled>
                <span class="material-symbols-outlined text-[14px]">add</span>New
              </button>
            </div>
            <div id="sessions-list" class="p-2 space-y-1">
              <p class="text-xs text-on-surface-variant/60 px-2 py-4 text-center">Select a project first</p>
            </div>
          </div>
        </div>

        <!-- Right: chat area -->
        <div class="flex-1 flex flex-col min-w-0" id="chat-main">
          <div class="flex-1 flex items-center justify-center">
            <div class="text-center">
              <span class="material-symbols-outlined text-5xl text-on-surface-variant/20 mb-4 block"
                    style="font-variation-settings:'FILL' 1">chat</span>
              <p class="text-on-surface-variant font-body text-sm">Select a project and session to begin</p>
              <p class="text-on-surface-variant/50 font-body text-xs mt-1">or create a new session</p>
            </div>
          </div>
        </div>

      </div>
    </div>`;

  bindSidebarEvents();
  await initChatPage(params.id ?? null);
}

// ── Initialization ────────────────────────────────────────────

async function initChatPage(preselectedProjectId) {
  // Load all projects into selector
  const projects = await loadProjects(appState.user.id);
  const sel = document.getElementById('project-select');
  projects.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.project_id;
    opt.textContent = p.title ?? 'Untitled';
    sel.appendChild(opt);
  });

  // Project select change
  sel.addEventListener('change', async () => {
    const pid = sel.value;
    if (!pid) {
      chatState.projectId = null;
      renderSessionsList([]);
      renderChatWelcome();
      return;
    }
    await selectProject(pid);
  });

  // If pre-selected from URL
  if (preselectedProjectId) {
    sel.value = preselectedProjectId;
    await selectProject(preselectedProjectId);
  }

  // New session button
  document.getElementById('btn-new-session')?.addEventListener('click', async () => {
    if (!chatState.projectId) return;
    await startNewSession();
  });
}

async function selectProject(projectId) {
  chatState.projectId = projectId;
  const proj = document.querySelector(`#project-select option[value="${projectId}"]`);
  chatState.projectTitle = proj?.textContent ?? '';

  document.getElementById('btn-new-session')?.removeAttribute('disabled');
  document.getElementById('sessions-list').innerHTML =
    `<div class="px-2 py-4">${skeleton(3)}</div>`;

  try {
    const sessions = await loadProjectSessions(projectId);
    renderSessionsList(sessions);
    if (!sessions.length) {
      renderChatWelcome();
    }
  } catch (err) {
    toast(err.message, 'error');
  }
}

function renderSessionsList(sessions) {
  const el = document.getElementById('sessions-list');
  if (!sessions.length) {
    el.innerHTML = `<p class="text-xs text-on-surface-variant/60 px-2 py-4 text-center">No sessions yet</p>`;
    return;
  }
  el.innerHTML = sessions.map(s => `
    <div class="group flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer transition-all session-item
                ${s.session_id === chatState.sessionId
                  ? 'bg-surface-container-lowest ring-1 ring-secondary/20 text-primary'
                  : 'hover:bg-surface-container-lowest/60 text-on-surface-variant hover:text-on-surface'}"
         data-session-id="${s.session_id}">
      <span class="material-symbols-outlined text-[16px] flex-shrink-0 text-secondary/60">chat_bubble</span>
      <div class="flex-1 min-w-0">
        <p class="text-xs font-semibold truncate">${escHtml(s.title ?? 'Untitled Session')}</p>
        <p class="text-[10px] text-on-surface-variant/60 mt-0.5">${timeAgo(s.updated_at)}</p>
      </div>
      <button class="btn-delete-session opacity-0 group-hover:opacity-100 p-1 rounded hover:text-error transition-all flex-shrink-0"
              data-session-id="${s.session_id}">
        <span class="material-symbols-outlined text-[14px]">delete</span>
      </button>
    </div>`).join('');

  // Bind session clicks
  el.querySelectorAll('.session-item').forEach(item => {
    item.addEventListener('click', async (e) => {
      if (e.target.closest('.btn-delete-session')) return;
      const sid = item.dataset.sessionId;
      await openSession(sid);
    });
  });

  // Bind delete buttons
  el.querySelectorAll('.btn-delete-session').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!confirm('Delete this session?')) return;
      try {
        await deleteSession(btn.dataset.sessionId, chatState.projectId);
        toast('Session deleted', 'success');
        const sessions = await loadProjectSessions(chatState.projectId);
        renderSessionsList(sessions);
        if (btn.dataset.sessionId === chatState.sessionId) renderChatWelcome();
      } catch (err) {
        toast(err.message, 'error');
      }
    });
  });
}

async function startNewSession() {
  try {
    const session = await createSession(chatState.projectId, appState.user.id);
    chatState.sessionId = session.session_id;
    chatState.messages  = [];
    const sessions = await loadProjectSessions(chatState.projectId);
    renderSessionsList(sessions);
    renderChatMain();
    renderMessages();
    toast('New session started', 'success');
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function openSession(sessionId) {
  chatState.sessionId = sessionId;
  renderChatMain();
  document.getElementById('chat-messages').innerHTML =
    `<div class="p-6">${skeleton(4)}</div>`;

  try {
    const { events } = await loadSessionHistory(sessionId);
    chatState.messages = events.map(ev => ({
      role:     ev.type,
      content:  getEventContent(ev),
      type:     ev.type,
      queryId:  ev.query_id,
      toolData: ev.type === 'tool_result' ? ev.data : null,
    }));
    renderMessages();
  } catch (err) {
    toast(err.message, 'error');
  }

  // Highlight selected session
  document.querySelectorAll('.session-item').forEach(el => {
    const active = el.dataset.sessionId === sessionId;
    el.classList.toggle('bg-surface-container-lowest', active);
    el.classList.toggle('ring-1', active);
    el.classList.toggle('ring-secondary/20', active);
    el.classList.toggle('text-primary', active);
  });
}

function getEventContent(ev) {
  let d = ev.data ?? {};
  if (typeof d === 'string') { try { d = JSON.parse(d); } catch { d = { content: d }; } }
  if (ev.type === 'human')       return d.content ?? '';
  if (ev.type === 'ai')          return d.token_stream ?? d.content ?? '';
  if (ev.type === 'tool_result') return d.tool_name ?? '';
  return '';
}

// ── Chat UI ───────────────────────────────────────────────────

function renderChatWelcome() {
  document.getElementById('chat-main').innerHTML = `
    <div class="flex-1 flex items-center justify-center">
      <div class="text-center">
        <span class="material-symbols-outlined text-5xl text-on-surface-variant/20 mb-4 block"
              style="font-variation-settings:'FILL' 1">chat</span>
        <p class="text-on-surface-variant font-body text-sm">Select a session or create a new one</p>
      </div>
    </div>`;
}

function renderChatMain() {
  document.getElementById('chat-main').innerHTML = `
    <!-- Project context bar -->
    <div class="px-6 py-3 border-b border-outline-variant/10 flex items-center gap-2 flex-shrink-0 bg-surface-container-low/50">
      <a href="#/project/${chatState.projectId}"
         class="flex items-center gap-1.5 text-xs text-on-surface-variant hover:text-primary transition-colors font-semibold">
        <span class="material-symbols-outlined text-[14px]">folder_open</span>
        ${escHtml(chatState.projectTitle)}
      </a>
      <span class="text-on-surface-variant/30 text-xs">·</span>
      <span class="text-xs text-on-surface-variant/60">Chat session</span>
    </div>

    <!-- Messages -->
    <div id="chat-messages" class="flex-1 overflow-y-auto p-6 space-y-4 font-body text-sm"></div>

    <!-- Input -->
    <div class="px-6 py-4 border-t border-outline-variant/10 bg-surface flex-shrink-0">
      <div class="flex items-center gap-2 mb-2">
        <span class="material-symbols-outlined text-[14px] text-on-surface-variant">smart_toy</span>
        <select id="model-select" class="text-xs text-on-surface-variant bg-transparent outline-none cursor-pointer">
          <option value="google_gemini-2.5-flash" selected>Gemini 2.5 Flash</option>
          <option value="google_gemini-2.5-pro">Gemini 2.5 Pro</option>
          <option value="anthropic_claude-sonnet-4-6">Claude Sonnet 4.6</option>
          <option value="anthropic_claude-haiku-4-5">Claude Haiku 4.5</option>
        </select>
      </div>
      <div class="flex items-end gap-2">
        <textarea id="chat-input" rows="3" placeholder="Ask a question about this case..."
          class="flex-1 resize-none bg-surface-container ring-1 ring-outline-variant/20 focus:ring-2 focus:ring-secondary
                 rounded-xl px-3.5 py-2.5 text-sm font-body outline-none transition-all placeholder:text-on-surface-variant/40">
        </textarea>
        <button id="btn-send"
          class="flex-shrink-0 p-2.5 rounded-xl bg-gradient-to-b from-primary to-primary-container text-on-primary
                 hover:opacity-90 transition-opacity disabled:opacity-40">
          <span class="material-symbols-outlined text-[20px]">send</span>
        </button>
      </div>
      <div class="mt-2 flex items-center gap-2">
        <label for="chat-file-upload" class="flex items-center gap-1.5 cursor-pointer text-xs text-on-surface-variant hover:text-secondary transition-colors">
          <span class="material-symbols-outlined text-[16px]">attach_file</span>Attach
        </label>
        <input id="chat-file-upload" type="file" class="hidden" multiple accept=".pdf,.txt,.eml,.csv,.xlsx,.pptx,.docx">
        <div id="file-chips" class="flex flex-wrap gap-1"></div>
      </div>
    </div>`;

  bindChatEvents();
  renderMessages();
}

function bindChatEvents() {
  document.getElementById('btn-send')?.addEventListener('click', () => sendMessage());
  document.getElementById('chat-input')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  document.getElementById('chat-file-upload')?.addEventListener('change', (e) => {
    chatState.pendingFiles = Array.from(e.target.files ?? []);
    renderFileChips();
  });
}

// ── Message sending ───────────────────────────────────────────

async function sendMessage() {
  if (chatState.streaming || !chatState.sessionId) return;
  const inputEl  = document.getElementById('chat-input');
  const question = inputEl?.value.trim();
  if (!question) return;

  const model   = document.getElementById('model-select')?.value ?? 'google_gemini-2.5-flash';
  const queryId = uuid();
  const attachments = await buildAttachmentPayloads(chatState.pendingFiles, queryId);
  chatState.pendingFiles = [];
  renderFileChips();

  inputEl.value = '';
  inputEl.disabled = true;
  document.getElementById('btn-send').disabled = true;

  chatState.messages.push({ role: 'human', content: question, type: 'human', queryId });
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
    project_id:  chatState.projectId,
  };

  _streamController = streamChat(request, {
    onToken: (token) => { aiMsg.content += token; updateStreamingMessage(aiMsg); },
    onReasoning: (text) => { aiMsg.reasoning = (aiMsg.reasoning ?? '') + text; updateStreamingMessage(aiMsg); },
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

// ── Rendering ─────────────────────────────────────────────────

function renderMessages(keepScroll = false) {
  const el = document.getElementById('chat-messages');
  if (!el) return;
  if (!chatState.messages.length) {
    el.innerHTML = `
      <div class="flex flex-col items-center justify-center h-full py-16 text-center">
        <span class="material-symbols-outlined text-4xl text-on-surface-variant/20 mb-3">chat_bubble</span>
        <p class="text-on-surface-variant text-sm">Ask a question to begin.</p>
      </div>`;
    return;
  }
  const wasAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
  el.innerHTML = chatState.messages.map(msg => renderMessage(msg)).join('');
  if (!keepScroll && (wasAtBottom || chatState.streaming)) el.scrollTop = el.scrollHeight;
}

function updateStreamingMessage(aiMsg) {
  const el = document.querySelector(`[data-query-id="${aiMsg.queryId}"].ai-message`);
  if (!el) { renderMessages(); return; }
  const contentEl = el.querySelector('.msg-content');
  if (contentEl) contentEl.innerHTML = md(aiMsg.content);
  const dotEl = el.querySelector('.streaming-dot');
  if (dotEl) dotEl.classList.toggle('hidden', !aiMsg.streaming);
  const msgs = document.getElementById('chat-messages');
  if (msgs) msgs.scrollTop = msgs.scrollHeight;
}

function renderMessage(msg) {
  if (msg.type === 'human') {
    return `
      <div class="flex justify-end">
        <div class="max-w-[80%] bg-primary-container text-on-primary rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed">
          ${escHtml(msg.content)}
        </div>
      </div>`;
  }
  if (msg.type === 'tool_result') {
    const toolName = msg.content || (msg.toolData?.tool_name ?? 'tool');
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
  return `
    <div class="flex items-start gap-2 ai-message" data-query-id="${msg.queryId ?? ''}">
      <div class="w-6 h-6 rounded-full bg-secondary-container flex items-center justify-center flex-shrink-0 mt-0.5">
        <span class="material-symbols-outlined text-[14px] text-secondary" style="font-variation-settings:'FILL' 1">smart_toy</span>
      </div>
      <div class="flex-1 min-w-0">
        ${msg.reasoning ? `
          <details class="mb-2 text-xs text-on-surface-variant">
            <summary class="cursor-pointer hover:text-primary font-bold">Reasoning</summary>
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
