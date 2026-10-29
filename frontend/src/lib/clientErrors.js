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
      }),
    }).catch(() => {});
  } catch {
    // Reporting a crash must never be the second crash.
  }
}

/** Test hook: switch reporting on or off and forget what was sent. */
export function _setEnabled(value) {
  enabled = value;
  sent = new Set();
  count = 0;
}
