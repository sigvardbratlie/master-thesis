// ============================================================
// ROUTER — simple hash-based client-side router
// Routes: #/ | #/project/:id | #/user | #/company
// ============================================================

class Router {
  constructor() {
    this._routes  = [];
    this._current = null;
    window.addEventListener('hashchange', () => this._resolve());
  }

  /** Register a route. Pattern supports :param segments. */
  on(pattern, handler) {
    this._routes.push({ pattern, handler, regex: this._toRegex(pattern) });
    return this;
  }

  /** Navigate to a path */
  navigate(path) {
    window.location.hash = path;
  }

  /** Start the router (resolve current hash) */
  start() {
    this._resolve();
  }

  _resolve() {
    const hash   = window.location.hash.slice(1) || '/';
    const path   = hash.split('?')[0];

    for (const route of this._routes) {
      const match = path.match(route.regex);
      if (match) {
        const params = this._extractParams(route.pattern, match);
        this._current = { path, params };
        route.handler(params);
        return;
      }
    }
  }

  _toRegex(pattern) {
    const escaped = pattern.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, '\\$&');
    const withParams = escaped.replace(/:([a-zA-Z]+)/g, '([^/]+)');
    return new RegExp(`^${withParams}$`);
  }

  _extractParams(pattern, match) {
    const keys   = (pattern.match(/:([a-zA-Z]+)/g) ?? []).map(k => k.slice(1));
    const values = match.slice(1);
    return Object.fromEntries(keys.map((k, i) => [k, values[i]]));
  }

  get current() {
    return this._current;
  }
}

export const router = new Router();
