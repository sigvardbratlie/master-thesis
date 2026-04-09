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

  const ICONS = {
    starting: '▶️',
    processing: '⏳',
    complete: '✅',
    ocr: '🔍',
    error: '❌',
  };

  const icon = ICONS[status] || '⚙️';

  const PHASE_MESSAGES = {
    collapse_emails:  'Collapsing email threads',
    extract_emails:   'Extracting email content',
    initialize_input: 'Analyzing case description',
    'loading-data':   'Loading project data',
    cleanup_elements: 'Cleaning factsheet elements',
    deduplication:    'Deduplicating factsheet elements',
    cleanup_metadata: 'Cleaning project metadata',
    storage:          'Saving files to secure storage',
    parsing:          'Parsing and extracting text from documents',
    parse_doc:        'Parsing document',
    parse_documents:  'Parsing documents',
    ocr:              'Running OCR on scanned pages',
    ocr_doc:          'Running OCR on document',
    embedding:        'Creating embeddings for semantic search',
    analyze:          'Analyzing documents and emails for key facts',
    analyze_docs:     'Analyzing documents',
    analyze_emails:   'Analyzing emails',
    update_metadata:  'Updating project summary',
    save:             'Saving results to project',
    qc_analysis:      'Running quality checks on analysis',
    load_project_data:'Loading existing project data',
  };

  const phaseNames = Array.isArray(phase) ? phase : [phase || 'unknown'];
  const translatedPhases = phaseNames.map(p => PHASE_MESSAGES[p] || `Unknown phase: ${p}`);
  let message = translatedPhases.join(' & ');

  let details = null;

  if (phaseNames.includes('parsing') && status === 'processing' && data?.filename) {
    message = `Parsing: ${data.filename}`;
  }

  if (phaseNames.includes('analyze') && status === 'processing' && data?.specs) {
    details = `Analyzing: ${data.specs}`;
  }

  return { icon, message, details };
}
