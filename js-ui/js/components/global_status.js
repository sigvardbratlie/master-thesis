// js-ui/js/components/global_status.js

import { mapStatusEvent } from './status_mapper.js';

const STATUS_ELEMENT_ID = 'global-pipeline-status';
const TEXT_ELEMENT_ID = 'global-pipeline-status-text';
const DETAILS_ELEMENT_ID = 'global-pipeline-status-details';
const CLOSE_BUTTON_ID = 'global-pipeline-status-close';

let _isVisible = false;

function ensureStatusElement() {
  if (document.getElementById(STATUS_ELEMENT_ID)) return;

  const element = document.createElement('div');
  element.id = STATUS_ELEMENT_ID;
  element.className = 'hidden fixed bottom-4 right-4 z-[1000] w-full max-w-sm';
  element.innerHTML = `
    <div class="bg-surface-container-high rounded-2xl shadow-2xl ring-1 ring-outline-variant/10 p-4">
      <div class="flex items-start gap-3">
        <div id="${TEXT_ELEMENT_ID}" class="flex-1 text-sm font-medium text-on-surface"></div>
        <button id="${CLOSE_BUTTON_ID}" class="p-1 rounded-lg hover:bg-surface-container">
          <span class="material-symbols-outlined text-base">close</span>
        </button>
      </div>
      <div id="${DETAILS_ELEMENT_ID}" class="text-xs text-on-surface-variant mt-1"></div>
    </div>
  `;
  document.body.appendChild(element);

  document.getElementById(CLOSE_BUTTON_ID).addEventListener('click', hideGlobalStatus);
}

/**
 * Shows the global status banner.
 */
export function showGlobalStatus() {
  ensureStatusElement();
  const el = document.getElementById(STATUS_ELEMENT_ID);
  if (el) {
    el.classList.remove('hidden');
    _isVisible = true;
  }
}

/**
 * Hides the global status banner.
 */
export function hideGlobalStatus() {
  const el = document.getElementById(STATUS_ELEMENT_ID);
  if (el) {
    el.classList.add('hidden');
    _isVisible = false;
  }
}

/**
 * Updates the status banner with a new event.
 * @param {import('./status_mapper.js').StatusEvent} event
 */
export function updateGlobalStatus(event) {
  if (!_isVisible) return;

  const { icon, message, details } = mapStatusEvent(event);
  const textEl = document.getElementById(TEXT_ELEMENT_ID);
  const detailsEl = document.getElementById(DETAILS_ELEMENT_ID);

  if (textEl) {
    textEl.textContent = `${icon} ${message}`;
  }
  if (detailsEl) {
    detailsEl.textContent = details || '';
    detailsEl.classList.toggle('hidden', !details);
  }
}

/**
 * Updates the banner to show a completion message.
 * @param {string} [message='✅ Process complete!']
 */
export function setGlobalStatusComplete(message = '✅ Process complete!') {
    if (!_isVisible) return;
    const textEl = document.getElementById(TEXT_ELEMENT_ID);
    const detailsEl = document.getElementById(DETAILS_ELEMENT_ID);
    if (textEl) {
        textEl.textContent = message;
    }
    if (detailsEl) {
        detailsEl.classList.add('hidden');
    }
}

/**
 * Updates the banner to show an error message.
 * @param {string} errorMessage
 */
export function setGlobalStatusError(errorMessage) {
    if (!_isVisible) return;
    const textEl = document.getElementById(TEXT_ELEMENT_ID);
    const detailsEl = document.getElementById(DETAILS_ELEMENT_ID);
    if (textEl) {
        textEl.textContent = `❌ Error: ${errorMessage}`;
    }
    if (detailsEl) {
        detailsEl.classList.add('hidden');
    }
}
