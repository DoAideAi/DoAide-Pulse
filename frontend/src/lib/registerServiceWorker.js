/**
 * Register `/sw.js` once the page has loaded.
 *
 * This used to be an inline <script> in index.html, which the SPA's CSP
 * (script-src 'self', no 'unsafe-inline') blocked — so the service worker never
 * installed and the install prompt never had a PWA to offer.
 */
export default function registerServiceWorker(nav = navigator, win = window) {
  if (!nav || !("serviceWorker" in nav)) return false;
  win.addEventListener("load", () => {
    nav.serviceWorker.register("/sw.js").catch(() => {});
  });
  return true;
}
