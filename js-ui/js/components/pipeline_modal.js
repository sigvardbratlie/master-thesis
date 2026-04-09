// ============================================================
// PIPELINE MODAL — shared component for project pipeline ops
// Used by both init-project (portfolio) and update-project (project dashboard).
// ============================================================

import { escHtml } from '../utils.js';
import { mapStatusEvent } from './status_mapper.js';
import { showGlobalStatus, hideGlobalStatus, startGlobalStatusLog, addGlobalStatusLogLine, setGlobalStatusComplete, setGlobalStatusError } from './global_status.js';

const MODEL_OPTIONS = [
  { value: 'google_gemini-2.5-flash', label: 'Google — Gemini 2.5 Flash' },
  { value: 'google_gemini-2.5-pro', label: 'Google — Gemini 2.5 Pro' },
  { value: 'anthropic_claude-sonnet-4-6', label: 'Anthropic — Claude Sonnet 4.6' },
  { value: 'anthropic_claude-haiku-4-5', label: 'Anthropic — Claude Haiku 4.5' },
];

const DEFAULT_MODEL = MODEL_OPTIONS[0]?.value ?? 'google_gemini-2.5-flash';

function _formatModelLabel(value) {
  const hit = MODEL_OPTIONS.find((m) => m.value === value);
  if (hit) return hit.label;

  const parts = String(value || '').split('_');
  const provider = parts.shift() || 'Unknown';
  const model = parts.join('_') || 'Unknown model';
  return `${provider[0]?.toUpperCase() || provider}${provider.slice(1)} — ${model.replace(/_/g, ' ')}`;
}

function _renderModelOptions(selectedValue = DEFAULT_MODEL) {
  return MODEL_OPTIONS.map((m) => `
    <option value="${m.value}" ${m.value === selectedValue ? 'selected' : ''}>${m.label}</option>`).join('');
}

// ── Render ───────────────────────────────────────────────────

/**
 * Returns the HTML string for a pipeline modal.
 *
 * @param {object} opts
 * @param {string} opts.id            - Unique modal ID prefix (e.g. 'init', 'update')
 * @param {string} opts.icon          - Material Symbols icon name
 * @param {string} opts.title         - Modal header title
 * @param {string} opts.description   - Modal header subtitle
 * @param {boolean} opts.showTitleInput  - Render project title field (init only)
 * @param {boolean} opts.contextRequired - Context textarea is required (init) vs optional (update)
 * @param {string} opts.runLabel         - Run button label
 */
export function renderPipelineModal({ id, icon, title, description, showTitleInput = false, contextRequired = false, runLabel }) {
  const titleField = showTitleInput ? `
    <label class="block text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-1.5">Project Title</label>
    <input
      id="${id}-modal-title"
      type="text"
      placeholder="e.g. Harrison v. Global Tech Solutions"
      class="w-full bg-surface-container ring-1 ring-outline-variant/20 focus:ring-2 focus:ring-secondary rounded-lg px-3.5 py-2.5 text-sm font-body outline-none transition-all mb-5"
    >` : '';

  return `
    <div id="${id}-modal" class="hidden fixed inset-0 z-[200] flex items-center justify-center p-4">
      <div id="${id}-backdrop" class="absolute inset-0 bg-black/30 backdrop-blur-sm"></div>
      <div class="relative bg-surface-container-lowest rounded-2xl shadow-[0_32px_80px_-16px_rgba(0,0,0,0.2)] w-full max-w-lg ring-1 ring-outline-variant/10 overflow-hidden flex flex-col max-h-[90vh]">

        <!-- Header -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-outline-variant/10 flex-shrink-0">
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-primary-container flex items-center justify-center">
              <span class="material-symbols-outlined text-white text-[16px]">${icon}</span>
            </div>
            <div>
              <h2 class="font-headline font-bold text-base text-primary">${title}</h2>
              <p class="text-[10px] text-on-surface-variant">${description}</p>
            </div>
          </div>
          <button id="${id}-close" class="p-1.5 rounded-lg hover:bg-surface-container text-on-surface-variant transition-colors">
            <span class="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        <!-- Body -->
        <div class="p-6 overflow-y-auto flex-1">

          ${titleField}

          <!-- Model -->
          <label class="block text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-1.5">Model</label>
          <select id="${id}-model"
            class="w-full bg-surface-container ring-1 ring-outline-variant/20 focus:ring-2 focus:ring-secondary rounded-lg px-3.5 py-2.5 text-sm font-body outline-none transition-all">
            ${_renderModelOptions(DEFAULT_MODEL)}
          </select>
          <p id="${id}-model-selected" class="text-[10px] text-on-surface-variant/60 mt-1 mb-5">Selected: ${_formatModelLabel(DEFAULT_MODEL)}</p>

          <!-- Context -->
          <label class="block text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-1.5">
            ${contextRequired
              ? 'Case Description'
              : `Additional Context <span class="text-on-surface-variant/40 font-normal normal-case">(optional)</span>`
            }
          </label>
          <textarea id="${id}-question" rows="3"
            placeholder="${contextRequired
              ? 'Briefly describe the case, parties involved, and key issues…'
              : 'Describe what to focus on or any additional context…'
            }"
            class="w-full bg-surface-container ring-1 ring-outline-variant/20 focus:ring-2 focus:ring-secondary rounded-lg px-3.5 py-2.5 text-sm font-body outline-none resize-none transition-all mb-5"></textarea>

          <!-- Drop zone -->
          <label id="${id}-dropzone"
            class="flex flex-col items-center justify-center border-2 border-dashed border-outline-variant rounded-xl p-10 text-center cursor-pointer
                   hover:border-secondary hover:bg-secondary/3 transition-all group">
            <input id="${id}-file-input" type="file" multiple class="hidden"
              accept=".pdf,.txt,.eml,.csv,.xlsx,.pptx,.docx">
            <span class="material-symbols-outlined text-4xl text-on-surface-variant/30 group-hover:text-secondary mb-3 transition-colors">upload_file</span>
            <p class="text-sm font-semibold text-on-surface-variant group-hover:text-primary transition-colors">
              Drop files here or click to browse
            </p>
            <p class="text-[11px] text-on-surface-variant/50 mt-1">PDF, DOCX, PPTX, TXT, EML, CSV, XLSX</p>
          </label>

          <!-- File list -->
          <div id="${id}-file-list" class="hidden mt-4 space-y-2"></div>

          <!-- Streaming log -->
          <div id="${id}-progress" class="hidden mt-4">
            <div class="flex items-center gap-2 mb-2">
              <span id="${id}-spinner" class="w-3 h-3 rounded-full bg-secondary animate-pulse"></span>
              <p class="text-xs font-bold text-secondary uppercase tracking-wider">Processing…</p>
            </div>
            <div id="${id}-log"
              class="bg-surface-container rounded-xl p-4 text-xs font-mono text-on-surface-variant overflow-y-auto max-h-40 space-y-1">
            </div>
          </div>

          <!-- Error -->
          <div id="${id}-error" class="hidden mt-4 p-3 bg-error-container/40 rounded-xl text-sm text-error font-body"></div>
        </div>

        <!-- Footer -->
        <div class="px-6 py-4 border-t border-outline-variant/10 flex gap-3 flex-shrink-0">
          <button id="${id}-cancel"
            class="flex-1 px-4 py-2.5 rounded-lg bg-surface-container text-on-surface font-headline font-semibold text-sm hover:bg-surface-container-high transition-colors">
            Cancel
          </button>
          <button id="${id}-run" disabled
            class="flex-1 px-4 py-2.5 rounded-lg bg-black text-white
                   font-headline font-semibold text-sm hover:opacity-90 active:scale-[0.98] transition-all
                   disabled:opacity-40 disabled:cursor-not-allowed">
            <span class="material-symbols-outlined text-[16px] align-middle mr-1">${icon}</span>
            ${runLabel}
          </button>
        </div>
      </div>
    </div>`;
}

// ── State (keyed by modal id) ─────────────────────────────────

const _state = {};

function _getState(id) {
  if (!_state[id]) _state[id] = { files: [], abort: null, isRunning: false, model: DEFAULT_MODEL };
  return _state[id];
}

// ── File list renderer ────────────────────────────────────────

function _renderFileList(id) {
  const st  = _getState(id);
  const el  = document.getElementById(`${id}-file-list`);
  const btn = document.getElementById(`${id}-run`);
  if (!el) return;

  if (!st.files.length) {
    el.classList.add('hidden');
    if (btn) btn.disabled = true;
    return;
  }

  el.classList.remove('hidden');
  el.innerHTML = st.files.map((f, i) => `
    <div class="flex items-center gap-3 px-3 py-2 bg-surface-container rounded-xl">
      <span class="material-symbols-outlined text-[18px] text-secondary">description</span>
      <div class="flex-1 min-w-0">
        <p class="text-xs font-semibold text-on-surface truncate">${escHtml(f.name)}</p>
        <p class="text-[10px] text-on-surface-variant">${(f.size / 1024).toFixed(0)} KB</p>
      </div>
      <button data-remove="${i}" class="p-1 rounded hover:bg-error-container/30 text-on-surface-variant hover:text-error transition-colors">
        <span class="material-symbols-outlined text-[16px]">close</span>
      </button>
    </div>`).join('');

  if (btn) btn.disabled = false;

  el.querySelectorAll('[data-remove]').forEach(removeBtn => {
    removeBtn.addEventListener('click', () => {
      st.files.splice(Number(removeBtn.dataset.remove), 1);
      _renderFileList(id);
    });
  });
}

// ── Open ─────────────────────────────────────────────────────

/**
 * Opens a pipeline modal and wires all events.
 *
 * @param {string} id               - Modal ID prefix (must match renderPipelineModal id)
 * @param {object} opts
 * @param {boolean} opts.showTitleInput   - Whether the title field is present
 * @param {boolean} opts.contextRequired  - Whether the context textarea must be filled
 * @param {Function} opts.onRun           - async ({ files, question, title?, model }, { logLine, setError, setDone, setAbort, onChunk }) => void
 */
export function openPipelineModal(id, { showTitleInput = false, contextRequired = false, onRun }) {
  const st    = _getState(id);
  st.files    = [];
  st.abort    = null;
  st.isRunning = false;
  const modal = document.getElementById(`${id}-modal`);
  if (!modal) return;

  // Reset UI
  hideGlobalStatus();
  document.getElementById(`${id}-file-list`).classList.add('hidden');
  document.getElementById(`${id}-file-list`).innerHTML = '';
  document.getElementById(`${id}-progress`).classList.add('hidden');
  document.getElementById(`${id}-log`).innerHTML = '';
  document.getElementById(`${id}-error`).classList.add('hidden');
  document.getElementById(`${id}-run`).disabled = true;
  document.getElementById(`${id}-file-input`).value = '';
  document.getElementById(`${id}-question`).value = '';
  document.getElementById(`${id}-cancel`).textContent = 'Cancel';
  if (showTitleInput) document.getElementById(`${id}-modal-title`).value = '';

  const modelSelect = document.getElementById(`${id}-model`);
  const modelLabel  = document.getElementById(`${id}-model-selected`);
  const updateModelLabel = (value) => {
    if (modelLabel) modelLabel.textContent = `Selected: ${_formatModelLabel(value)}`;
  };
  if (modelSelect) {
    modelSelect.value = st.model ?? DEFAULT_MODEL;
    updateModelLabel(modelSelect.value);
    modelSelect.onchange = () => {
      st.model = modelSelect.value;
      updateModelLabel(modelSelect.value);
    };
  }

  modal.classList.remove('hidden');
  (showTitleInput
    ? document.getElementById(`${id}-modal-title`)
    : document.getElementById(`${id}-question`)
  )?.focus();

  // ── File input ──────────────────────────────────────────────
  const fileInput = document.getElementById(`${id}-file-input`);
  const onFileChange = (e) => {
    st.files = Array.from(e.target.files);
    _renderFileList(id);
  };
  fileInput.addEventListener('change', onFileChange, { once: true });

  // ── Drag-and-drop ───────────────────────────────────────────
  const dz = document.getElementById(`${id}-dropzone`);
  const onDragOver  = (e) => { e.preventDefault(); dz.classList.add('border-secondary'); };
  const onDragLeave = ()  => dz.classList.remove('border-secondary');
  const onDrop = (e) => {
    e.preventDefault();
    dz.classList.remove('border-secondary');
    if (st.isRunning) return;
    st.files = Array.from(e.dataTransfer.files);
    _renderFileList(id);
  };
  dz.addEventListener('dragover',  onDragOver);
  dz.addEventListener('dragleave', onDragLeave);
  dz.addEventListener('drop',      onDrop, { once: true });

  // ── Close ───────────────────────────────────────────────────
  function closeModal() {
    if (st.isRunning) {
      showGlobalStatus();
    } else {
      st.abort?.abort();
    }
    modal.classList.add('hidden');
    dz.removeEventListener('dragover',  onDragOver);
    dz.removeEventListener('dragleave', onDragLeave);
  }
  document.getElementById(`${id}-close`)?.addEventListener('click',    closeModal, { once: true });
  document.getElementById(`${id}-cancel`)?.addEventListener('click',   closeModal, { once: true });
  document.getElementById(`${id}-backdrop`)?.addEventListener('click', closeModal, { once: true });

  // ── Run ─────────────────────────────────────────────────────
  // No { once: true } — validation may return early, and we must allow retry.
  // Button is disabled programmatically once a run actually starts.
  const runBtn = document.getElementById(`${id}-run`);
  const onRunClick = async () => {
    if (!st.files.length && contextRequired) return; // Allow running with no files if context is not required (e.g. update)

    const errEl = document.getElementById(`${id}-error`);

    const titleValue = showTitleInput
      ? document.getElementById(`${id}-modal-title`)?.value.trim()
      : null;

    if (showTitleInput && !titleValue) {
      errEl.textContent = 'Please enter a project title.';
      errEl.classList.remove('hidden');
      return;
    }

    const question = document.getElementById(`${id}-question`)?.value.trim();
    if (contextRequired && !question) {
      errEl.textContent = 'Please provide a case description.';
      errEl.classList.remove('hidden');
      return;
    }

    const modelValue = document.getElementById(`${id}-model`)?.value ?? DEFAULT_MODEL;
    st.model = modelValue;

    // ── Commit to running — close modal immediately, hand off to status panel ─
    st.isRunning = true;
    runBtn.disabled = true;
    runBtn.removeEventListener('click', onRunClick);

    // Remove stale close listeners so they don't fire on next modal open
    document.getElementById(`${id}-close`)?.removeEventListener('click',    closeModal);
    document.getElementById(`${id}-cancel`)?.removeEventListener('click',   closeModal);
    document.getElementById(`${id}-backdrop`)?.removeEventListener('click', closeModal);

    const runTitle = document.querySelector(`#${id}-modal h2`)?.textContent?.trim() || 'Processing…';
    const modelLabelText = _formatModelLabel(modelValue);
    modal.classList.add('hidden');
    dz.removeEventListener('dragover',  onDragOver);
    dz.removeEventListener('dragleave', onDragLeave);
    startGlobalStatusLog(`${runTitle} · ${modelLabelText}`);

    function logLine(event) {
      addGlobalStatusLogLine(event);
    }

    function setError(msg) {
      setGlobalStatusError(msg);
      st.isRunning = false;
    }

    function setDone(message = '✅ Done.') {
      setGlobalStatusComplete(message);
      st.isRunning = false;
    }

    function setAbort(ctrl) {
      st.abort = ctrl;
    }

    try {
      await onRun(
        { files: st.files, question, title: titleValue, model: modelValue },
        { logLine, setError, setDone, setAbort, onChunk: logLine },
      );
    } catch (err) {
      setError(err.message ?? String(err));
    }
  };
  runBtn?.addEventListener('click', onRunClick);
}
