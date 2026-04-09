// ============================================================
// CHAT PAGE — project-scoped chat workspace
// ============================================================

import {
  loadProjectMeta, loadProjectSessions, loadSessionHistory,
  createSession, deleteSession, streamChat,
  loadProjectAttachments, loadProjectEmails,
} from '../api.js';
import { renderProjectSidebar, bindProjectSidebarEvents } from '../components/sidebar_level2.js';
import { renderTopbar }                     from '../components/topbar.js';
import { appState }                         from '../state.js';
import { formatDate, timeAgo, toast, skeleton, uuid, escHtml, arrayBufferToBase64, resolveFileType } from '../utils.js';
import { marked }                           from 'marked';
import { chatLog }                          from '../logger.js';

marked.setOptions({ breaks: true, gfm: true });
const md = (text) => marked.parse(text ?? '');

let _streamController = null;
let _docsPanelLoaded  = false;

const chatState = {
  projectId:    null,
  projectTitle: '',
  sessionId:    null,
  messages:     [],
  pendingFiles: [],
  streaming:    false,
  focusedDocs:  [], // { id, name, type: 'attachment'|'email' }
};

// ── Entry point ───────────────────────────────────────────────

export async function renderChat(params = {}) {
  const projectId = params.id ?? null;

  // Reset panel state on navigation
  _docsPanelLoaded = false;
  chatState.focusedDocs = [];

  document.getElementById('app').innerHTML = `
    ${renderProjectSidebar(projectId ?? '')}
    <div class="ml-64 h-screen bg-surface flex flex-col overflow-hidden">
      ${renderTopbar({
        title: 'Chat',
        breadcrumb: projectId ? { label: 'Project', href: `#/project/${projectId}` } : undefined,
      })}
      <div class="flex-1 flex min-h-0 overflow-hidden">

        <!-- Sessions panel -->
        <div class="w-64 flex-shrink-0 border-r border-outline-variant/10 bg-surface-container-low flex flex-col overflow-hidden">
          <div class="p-4 border-b border-outline-variant/10 flex items-center justify-between flex-shrink-0">
            <p class="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">Sessions</p>
            <button id="btn-new-session"
              class="flex items-center gap-1 text-xs text-secondary hover:text-primary font-semibold transition-colors disabled:opacity-40"
              disabled>
              <span class="material-symbols-outlined text-[14px]">add</span>New
            </button>
          </div>
          <div id="sessions-list" class="flex-1 overflow-y-auto p-2 space-y-1">
            <div class="px-2 py-4">${skeleton(3)}</div>
          </div>
        </div>

        <!-- Chat area -->
        <div class="flex-1 flex flex-col min-w-0" id="chat-main">
          <div class="flex-1 flex items-center justify-center">
            <div class="text-center">
              <p class="text-on-surface-variant font-body text-sm">Select a session or create a new one</p>
            </div>
          </div>
        </div>

        <!-- Collapsible context filter panel -->
        <div id="docs-panel-wrap"
          class="flex-shrink-0 overflow-hidden border-l border-outline-variant/10 transition-[width] duration-200"
          style="width:0">
          <div class="w-64 h-full bg-surface-container-low flex flex-col">
            <div class="p-4 border-b border-outline-variant/10 flex-shrink-0">
              <div class="flex items-center justify-between mb-0.5">
                <p class="text-xs font-bold text-on-surface-variant">Focus Context</p>
                <button id="btn-close-docs"
                  class="p-0.5 rounded hover:bg-surface-container text-on-surface-variant/40 hover:text-on-surface-variant transition-colors">
                  <span class="material-symbols-outlined text-[16px]">close</span>
                </button>
              </div>
              <p class="text-[10px] text-on-surface-variant/50">Limit answer to selected files</p>
            </div>
            <div id="docs-panel-content" class="flex-1 overflow-y-auto p-3">
              <div class="py-4">${skeleton(4)}</div>
            </div>
          </div>
        </div>

      </div>
    </div>`;

  bindProjectSidebarEvents();
  await initChatPage(projectId);
}

// ── Initialization ────────────────────────────────────────────

async function initChatPage(projectId) {
  if (!projectId) {
    document.getElementById('sessions-list').innerHTML =
      `<p class="text-xs text-on-surface-variant/60 px-2 py-4 text-center">No project selected</p>`;
    return;
  }

  try {
    const meta = await loadProjectMeta(projectId);
    chatState.projectId    = projectId;
    chatState.projectTitle = meta?.title ?? '';
  } catch {
    chatState.projectId    = projectId;
    chatState.projectTitle = '';
  }

  document.getElementById('btn-new-session')?.removeAttribute('disabled');

  try {
    const sessions = await loadProjectSessions(projectId);
    renderSessionsList(sessions);
    if (!sessions.length) renderChatWelcome();
  } catch (err) {
    toast(err.message, 'error');
  }

  document.getElementById('btn-new-session')?.addEventListener('click', async () => {
    if (!chatState.projectId) return;
    await startNewSession();
  });
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

  el.querySelectorAll('.session-item').forEach(item => {
    item.addEventListener('click', async (e) => {
      if (e.target.closest('.btn-delete-session')) return;
      await openSession(item.dataset.sessionId);
    });
  });

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
        <p class="text-on-surface-variant font-body text-sm">Select a session or create a new one</p>
      </div>
    </div>`;
}

function renderChatMain() {
  document.getElementById('chat-main').innerHTML = `
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
      <div class="mt-2 flex items-center gap-3">
        <label for="chat-file-upload" class="flex items-center gap-1.5 cursor-pointer text-xs text-on-surface-variant hover:text-secondary transition-colors">
          <span class="material-symbols-outlined text-[16px]">attach_file</span>Attach
        </label>
        <input id="chat-file-upload" type="file" class="hidden" multiple accept=".pdf,.txt,.eml,.csv,.xlsx,.pptx,.docx">
        <div id="file-chips" class="flex flex-wrap gap-1 flex-1"></div>
        <!-- Focus filter toggle -->
        <button id="btn-toggle-docs" title="Filter context"
          class="flex items-center gap-1 text-xs text-on-surface-variant hover:text-secondary transition-colors ml-auto">
          <span class="material-symbols-outlined text-[16px]">filter_list</span>
          <span id="focus-badge" class="hidden text-[10px] font-bold bg-secondary text-on-primary px-1.5 rounded-full"></span>
        </button>
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
  document.getElementById('btn-toggle-docs')?.addEventListener('click', () => {
    toggleDocsPanel();
  });
  document.getElementById('btn-close-docs')?.addEventListener('click', () => {
    setDocsPanel(false);
  });
}

// ── Docs filter panel ─────────────────────────────────────────

function toggleDocsPanel() {
  const wrap = document.getElementById('docs-panel-wrap');
  const isOpen = wrap?.style.width !== '0px' && wrap?.style.width !== '0';
  setDocsPanel(!isOpen);
}

function setDocsPanel(open) {
  const wrap = document.getElementById('docs-panel-wrap');
  if (!wrap) return;
  wrap.style.width = open ? '256px' : '0';
  if (open && !_docsPanelLoaded) {
    _docsPanelLoaded = true;
    loadDocsPanel(chatState.projectId);
  }
}

async function loadDocsPanel(projectId) {
  const content = document.getElementById('docs-panel-content');
  if (!content || !projectId) return;

  try {
    const [attachments, emails] = await Promise.all([
      loadProjectAttachments(projectId).catch(() => []),
      loadProjectEmails(projectId).catch(() => []),
    ]);

    const attItems = (attachments ?? []).map(a => docCheckItem(
      `att-${a.file_id}`, a.filename ?? 'Attachment', 'attachment', a.file_id, a.filename ?? '',
    ));
    const emailItems = (emails ?? []).map(e => docCheckItem(
      `em-${e.email_id ?? e.message_id}`, e.subject ?? 'Email', 'email',
      e.email_id ?? e.message_id, e.subject ?? 'Email',
    ));

    content.innerHTML = `
      ${attItems.length ? `
        <p class="text-[9px] font-bold uppercase tracking-widest text-on-surface-variant/40 px-1 mb-1.5">Documents</p>
        <div class="space-y-0.5 mb-4">${attItems.join('')}</div>` : ''}
      ${emailItems.length ? `
        <p class="text-[9px] font-bold uppercase tracking-widest text-on-surface-variant/40 px-1 mb-1.5">Emails</p>
        <div class="space-y-0.5">${emailItems.join('')}</div>` : ''}
      ${!attItems.length && !emailItems.length
        ? `<p class="text-xs text-on-surface-variant/50 py-4 text-center">No files found</p>`
        : `<button id="btn-clear-focus" class="w-full mt-4 text-[10px] font-bold text-on-surface-variant/40 hover:text-error transition-colors py-1">
             Clear selection
           </button>`}`;

    content.querySelectorAll('.doc-check').forEach(cb => {
      cb.addEventListener('change', () => {
        if (cb.checked) {
          chatState.focusedDocs.push({ id: cb.dataset.id, name: cb.dataset.name, type: cb.dataset.type });
        } else {
          chatState.focusedDocs = chatState.focusedDocs.filter(d => d.id !== cb.dataset.id);
        }
        updateFocusBadge();
      });
    });

    document.getElementById('btn-clear-focus')?.addEventListener('click', () => {
      chatState.focusedDocs = [];
      content.querySelectorAll('.doc-check').forEach(cb => { cb.checked = false; });
      updateFocusBadge();
    });
  } catch (err) {
    content.innerHTML = `<p class="text-xs text-error px-2 py-4">${err.message}</p>`;
  }
}

function docCheckItem(checkId, label, type, id, name) {
  const icon = type === 'email' ? 'mail' : 'description';
  return `
    <label class="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-surface-container cursor-pointer group">
      <input type="checkbox" id="${checkId}" class="doc-check accent-secondary flex-shrink-0"
             data-id="${escHtml(id)}" data-name="${escHtml(name)}" data-type="${type}">
      <span class="material-symbols-outlined text-[13px] text-on-surface-variant/50 flex-shrink-0">${icon}</span>
      <span class="text-[11px] text-on-surface-variant group-hover:text-on-surface truncate leading-tight">${escHtml(label)}</span>
    </label>`;
}

function updateFocusBadge() {
  const badge = document.getElementById('focus-badge');
  if (!badge) return;
  const count = chatState.focusedDocs.length;
  if (count > 0) {
    badge.textContent = count;
    badge.classList.remove('hidden');
  } else {
    badge.classList.add('hidden');
  }
}

// ── Message sending ───────────────────────────────────────────

async function sendMessage() {
  if (chatState.streaming || !chatState.sessionId) return;
  const inputEl    = document.getElementById('chat-input');
  const rawQuestion = inputEl?.value.trim();
  if (!rawQuestion) return;

  const model   = document.getElementById('model-select')?.value ?? 'google_gemini-2.5-flash';
  const queryId = uuid();
  const attachments = await buildAttachmentPayloads(chatState.pendingFiles, queryId);
  chatState.pendingFiles = [];
  renderFileChips();

  inputEl.value = '';
  inputEl.disabled = true;
  document.getElementById('btn-send').disabled = true;

  // Build payload question — prepend focus context if files are selected
  const focusCtx = chatState.focusedDocs.length
    ? `[Focus on: ${chatState.focusedDocs.map(d => d.name).join(', ')}]\n\n`
    : '';
  const payloadQuestion = focusCtx + rawQuestion;

  chatState.messages.push({ role: 'human', content: rawQuestion, type: 'human', queryId });
  const aiMsg = { role: 'ai', content: '', type: 'ai', queryId, streaming: true };
  chatState.messages.push(aiMsg);
  chatState.streaming = true;
  renderMessages();

  const request = {
    question:    payloadQuestion,
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
    const base64 = arrayBufferToBase64(bytes);
    const fileId = uuid();
    return {
      filename:  file.name,
      file_id:   fileId,
      content:   base64,
      path:      `${appState.user.id}/${chatState.sessionId}/${fileId}${file.name.slice(file.name.lastIndexOf('.'))}`,
      file_type: resolveFileType(file),
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
  // AI message — no robot icon
  return `
    <div class="flex flex-col ai-message" data-query-id="${msg.queryId ?? ''}">
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
