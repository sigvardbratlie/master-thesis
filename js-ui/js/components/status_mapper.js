// js-ui/js/components/status_mapper.js

/**
 * @typedef {object} StatusEvent
 * @property {string[]} phase
 * @property {'starting' | 'processing' | 'complete' | 'ocr' | 'error'} status
 * @property {object} [data]
 */

/**
 * Maps a backend pipeline status event to a user-friendly object.
 * @param {StatusEvent} event
 * @returns {{icon: string, message: string, details: string|null}}
 */
export function mapStatusEvent(event) {
  const { phase, status, data } = event;
  const phaseName = phase?.[0] || 'unknown';

  const ICONS = {
    starting: '▶️',
    processing: '⏳',
    complete: '✅',
    ocr: '🔍',
    error: '❌',
  };

  const icon = ICONS[status] || '⚙️';

  const MESSAGES = {
    collapse_emails: 'Collapsing email threads',
    extract_emails: 'Extracting email content',
    initialize_input: 'Analyzing case description',
    storage: 'Saving files to secure storage',
    parsing: 'Parsing and extracting text from documents',
    embedding: 'Creating embeddings for semantic search',
    analyze: 'Analyzing documents and emails for key facts',
    update_metadata: 'Updating project summary',
    save: 'Saving results to project',
    qc_analysis: 'Running quality checks on analysis',
    load_project_data: 'Loading existing project data',
  };

  let message = MESSAGES[phaseName] || `Unknown phase: ${phaseName}`;
  let details = null;

  if (phaseName === 'parsing' && status === 'processing' && data?.filename) {
    message = `Parsing: ${data.filename}`;
  }

  if (phaseName === 'analyze' && status === 'processing' && data?.specs) {
    details = `Analyzing: ${data.specs}`;
  }
  
  if (status === 'complete' && phaseName in MESSAGES) {
    message = `${MESSAGES[phaseName]}`;
  }

  return { icon, message, details };
}
