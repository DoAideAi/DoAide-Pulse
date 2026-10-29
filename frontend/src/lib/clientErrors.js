import { routePattern } from "./activity";

// Where an error boundary reports a render crash (backend/app/routers/
// client_errors.py). Before this, a boundary that tripped showed its fallback
// panel and React wrote the stack to that one browser's console — so a page
// that crashed for everybody after a deploy was invisible to whoever runs
// Pulse until somebody wrote in.
const ENDPOINT = "/api/v1/client-errors";
const TOKEN_KEY = "pulse_token";
// A boundary inside a list can trip once per row; one page load says what it
// has to say in a handful of reports, and the server limits the rest anyway.
const MAX_PER_PAGE = 5;
// The commit this bundle was built from (vite.config.js `define`). Without it
// every report was logged release=-, and after a deploy nothing told a crash in
// the new code from one in a tab still running the old bundle.
const RELEASE = typeof __PULSE_RELEASE__ === "string" ? __PULSE_RELEASE__ : "";

let enabled = import.meta.env?.MODE !== "test";
let sent = new Set();
let count = 0;

/**
 * Component names from React's component stack, innermost first.
 *
 * Chrome writes ``at Name (url)``, Firefox and Safari ``Name@url``, and React's
 * own dev stack ``in Name``. Names only: the URLs are bundle paths, and a
 * hashed chunk name says nothing a reader can act on.
 */
export function componentNames(stack) {
  const names = [];
  for (const line of String(stack || "").split("\n")) {
    const match =
      line.match(/^\s*at\s+([A-Za-z_$][\w$.]*)/) ||
      line.match(/^\s*in\s+([A-Za-z_$][\w$.]*)/) ||
      line.match(/^\s*([A-Za-z_$][\w$.]*)@/);
    if (match) names.push(match[1]);
    if (names.length >= 12) break;
  }
  return names;
}

function token() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

/** Tell the server a boundary caught *error*. Fire-and-forget; never throws. */
export function reportRenderError(error, info, section) {
  if (!enabled || count >= MAX_PER_PAGE) return;
  try {
    const route = routePattern(typeof window !== "undefined" ? window.location.pathname : "/");
    const name = String(error?.name || "Error");
    const message = String(error?.message || error || "").slice(0, 2000);
    const signature = `${section || ""}|${route}|${name}|${message}`;
    if (sent.has(signature)) return;
    sent.add(signature);
    count += 1;

    const headers = { "Content-Type": "application/json" };
    const t = token();
    if (t) headers.Authorization = `Bearer ${t}`;
    fetch(ENDPOINT, {
      method: "POST",
      keepalive: true,
      headers,
      body: JSON.stringify({
        section: section || "",
        route,
        name,
        message,
        components: componentNames(info?.componentStack),
        release: RELEASE,
      }),
    }).catch(() => {});
  } catch {
    // Reporting a crash must never be the second crash.
  }
}

/**
 * Messages that are not Pulse's failure to report. "Script error." is all a
 * browser will say about a throw in a cross-origin script (an extension, an
 * analytics tag); the ResizeObserver line is a benign notice browsers raise
 * as an error event.
 */
const NOT_OURS = [/^Script error\.?$/, /^ResizeObserver loop/];

/**
 * Report throws an error boundary never sees: from event handlers, timers and
 * promises nobody handled. Those are the commonest front-end failures, and
 * they went to one browser's console and nowhere else. Returns a function that
 * stops listening.
 *
 * An API refusal is left out: every `request()` failure carries its HTTP
 * `status`, the server has its own line for it, and the page already showed
 * the person what went wrong. Reports share the per-page cap with render
 * crashes, so a handler that throws on every keystroke is five lines, not a
 * flood.
 */
export function reportUncaughtErrors() {
  if (typeof window === "undefined") return () => {};
  const onError = (event) => {
    const message = String(event?.message || event?.error?.message || "");
    if (NOT_OURS.some((pattern) => pattern.test(message))) return;
    reportRenderError(event?.error || new Error(message), { componentStack: event?.error?.stack }, "window:error");
  };
  const onRejection = (event) => {
    const reason = event?.reason;
    if (typeof reason?.status === "number") return;
    const error = reason instanceof Error ? reason : new Error(String(reason));
    reportRenderError(error, { componentStack: error.stack }, "window:unhandledrejection");
  };
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);
  return () => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
  };
}

/** Test hook: switch reporting on or off and forget what was sent. */
export function _setEnabled(value) {
  enabled = value;
  sent = new Set();
  count = 0;
}
