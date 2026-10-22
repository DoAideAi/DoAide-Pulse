import { lazy } from "react";

/**
 * `React.lazy`, plus one recovery a deploy makes necessary.
 *
 * Every page is its own chunk with a content hash in its name, and a deploy
 * replaces `dist/` wholesale. A tab opened before the deploy still runs the old
 * entry, which asks for the old chunk names — and those are gone. The import
 * rejects, the route's error boundary shows "This page stopped working", and
 * nothing the user does short of a hard reload fixes it.
 *
 * So the first failed chunk load reloads the page, which fetches the new entry
 * and its new chunk names. The flag in sessionStorage keeps that to once: a
 * chunk that fails for a real reason (offline, a broken build) must reach the
 * boundary rather than loop the tab through reloads. A successful load clears
 * it, so the next deploy gets its one reload too.
 */
export const RELOAD_FLAG = "pulse:chunk-reload";

function storage() {
  try {
    return window.sessionStorage ?? null;
  } catch {
    return null;
  }
}

export function loadWithReload(importer, { reload = () => window.location.reload() } = {}) {
  return importer().then(
    (module) => {
      storage()?.removeItem(RELOAD_FLAG);
      return module;
    },
    (error) => {
      const store = storage();
      if (store && !store.getItem(RELOAD_FLAG)) {
        store.setItem(RELOAD_FLAG, "1");
        reload();
        // Never settles: the page is going away, and resolving or rejecting
        // here would flash a fallback for the instant before it does.
        return new Promise(() => {});
      }
      throw error;
    },
  );
}

export default function lazyPage(importer) {
  return lazy(() => loadWithReload(importer));
}
