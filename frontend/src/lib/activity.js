// What the signed-in user looked at and did, recorded to Pulse's own database.
//
// Events queue here and leave in batches: on a short timer, when the queue
// fills, and when the tab is hidden. Nothing about it is load-bearing — a batch
// that cannot be sent is dropped, never retried, because the page the user is
// on matters more than the record that they were on it.
//
// Two kinds of event:
//   page_view — the route pattern ("/content/:id"), from `trackPageView`.
//   action    — a write the user made ("POST /content/:id/approve"), recorded by
//               `api.js` after the request succeeds, or a named event passed to
//               `trackEvent` ("login", "share").
//
// Query strings are dropped before anything is queued: they carry search text
// and filters, which is more than "which page" needs to say.

const ENDPOINT = "/api/v1/activity";
const TOKEN_KEY = "pulse_token";
const FLUSH_MS = 5000;
const MAX_QUEUE = 20;
const NAME_MAX = 80;
const PATH_MAX = 300;

let queue = [];
let timer = null;
// Off under vitest so a stray flush can never take a mocked fetch response
// another test queued. The tracker's own tests switch it on.
let enabled = import.meta.env?.MODE !== "test";

/** Collapse ids so "/content/42" and "/content/43" count as one page. */
export function routePattern(path) {
  const bare = String(path || "/").split(/[?#]/)[0] || "/";
  return redactSecrets(bare)
    .split("/")
    .map((seg) => (/^\d+$/.test(seg) || /^[0-9a-f-]{32,36}$/i.test(seg) ? ":id" : seg))
    .join("/");
}

/** Path segments that follow these are credentials, whatever they look like. */
const SECRET_SEGMENTS = { preview: ":token" };

/**
 * ``path`` with credential segments replaced — ``/preview/<token>`` becomes
 * ``/preview/:token``. A preview token is 43 URL-safe characters, neither a
 * number nor a UUID, so ``routePattern`` passed it through and it was stored
 * verbatim, as the event name and as its path, for anyone signed in who opened
 * one: the bearer credential the backend keeps only as a hash. The same rule
 * as ``public/analytics-redact.js`` applies to what Umami sees.
 */
export function redactSecrets(path) {
  const parts = String(path).split("/");
  for (let i = 1; i < parts.length; i++) {
    const hidden = SECRET_SEGMENTS[parts[i - 1]];
    if (hidden && parts[i]) parts[i] = hidden;
  }
  return parts.join("/");
}

function token() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function currentPath() {
  return typeof window !== "undefined" ? window.location.pathname : null;
}

function enqueue(kind, name, path) {
  // Signed-out pages are not recorded: the endpoint needs an account to file
  // the event under, and a landing-page visitor does not have one.
  if (!enabled || !token() || !name) return;
  queue.push({
    kind,
    name: String(name).slice(0, NAME_MAX),
    path: path ? redactSecrets(String(path).split(/[?#]/)[0]).slice(0, PATH_MAX) : null,
  });
  if (queue.length >= MAX_QUEUE) flush();
  else if (!timer) timer = setTimeout(flush, FLUSH_MS);
}

export function trackPageView(path) {
  enqueue("page_view", routePattern(path), path);
}

export function trackAction(name, path = currentPath()) {
  enqueue("action", name, path);
}

/** Send whatever is queued. Fire-and-forget; failures are swallowed. */
export function flush() {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  const t = token();
  if (!queue.length || !t) {
    queue = [];
    return;
  }
  const events = queue;
  queue = [];
  try {
    // keepalive lets the request outlive the page when it is sent on pagehide.
    fetch(ENDPOINT, {
      method: "POST",
      keepalive: true,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${t}` },
      body: JSON.stringify({ events }),
    }).catch(() => {});
  } catch {
    // Tracking must never break the app.
  }
}

if (typeof window !== "undefined") {
  window.addEventListener("pagehide", flush);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flush();
  });
}

/** Test hook: switch the tracker on or off and empty the queue. */
export function _setEnabled(value) {
  enabled = value;
  queue = [];
  if (timer) clearTimeout(timer);
  timer = null;
}
