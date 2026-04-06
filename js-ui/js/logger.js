// ============================================================
// LOGGER — pino browser logger
//
// Logs vises i:  F12 → Console (filtrer på [INFO], [ERROR] etc.)
// Buffer leses:  window.__logs  (maks 500 linjer, i minnet)
//
// NB: Browser-apper kan ikke skrive til fil direkte.
//     Backend-logs (FastAPI) ligger i terminalen via Python logging.
// ============================================================

import pino from 'pino';

const isDev   = import.meta.env.DEV;
const MAX_BUF = 500;

// In-memory ring buffer (tilgjengelig via window.__logs i DevTools)
const _buf = [];
window.__logs = _buf;

function _push(level, obj) {
  const entry = { ts: new Date().toISOString(), level, ...obj };
  if (_buf.length >= MAX_BUF) _buf.shift();
  _buf.push(entry);
}

export const logger = pino({
  level: isDev ? 'debug' : 'info',
  browser: {
    write: {
      trace: (o) => { console.debug('%c[TRACE]', 'color:#888', o.msg ?? o); _push('trace', o); },
      debug: (o) => { console.debug('%c[DEBUG]', 'color:#888', o.msg ?? o); _push('debug', o); },
      info:  (o) => { console.info ('%c[INFO] ', 'color:#3e608e;font-weight:bold', o.msg ?? o); _push('info',  o); },
      warn:  (o) => { console.warn ('%c[WARN] ', 'color:#ae7a01;font-weight:bold', o.msg ?? o); _push('warn',  o); },
      error: (o) => { console.error('%c[ERROR]', 'color:#ba1a1a;font-weight:bold', o.msg ?? o); _push('error', o); },
      fatal: (o) => { console.error('%c[FATAL]', 'color:#ba1a1a;font-weight:bold', o.msg ?? o); _push('fatal', o); },
    },
  },
});

// Modul-spesifikke child loggers
export const authLog   = logger.child({ module: 'auth'   });
export const apiLog    = logger.child({ module: 'api'    });
export const routerLog = logger.child({ module: 'router' });
export const cacheLog  = logger.child({ module: 'cache'  });
export const chatLog   = logger.child({ module: 'chat'   });

// Hjelpefunksjon: dump buffer til konsoll (skriv  __dumpLogs()  i DevTools)
window.__dumpLogs = () => {
  console.table(_buf.slice(-100));
};
