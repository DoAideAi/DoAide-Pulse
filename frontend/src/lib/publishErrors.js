/**
 * What to do about a publication's error, in a sentence.
 *
 * The backend stores the platform's own wording on the row — on purpose, it is
 * the evidence — and that wording is written for whoever debugs the adapter,
 * not whoever is looking at a red row on the Publish page. "Hashnode rejected
 * the request: Unauthorized" is accurate and says nothing about where to go.
 *
 * This reads the stored message and answers the second question only. It never
 * replaces the raw text, which stays visible beside it; an unrecognised error
 * gets no hint rather than a guessed one.
 *
 * Returns `{ kind, hint, action }` or `null`. `action`, when present, is
 * `{ label, to }` for a link the page can render.
 */
const SETTINGS = { label: "Open Settings", to: "/settings" };

const RULES = [
  {
    kind: "not_connected",
    test: /no live \S+ connection/i,
    hint: "This platform isn't connected. Connect it, then retry.",
    action: SETTINGS,
  },
  {
    kind: "credentials",
    test: /\b(401|403)\b|unauthori[sz]ed|forbidden|invalid (api[ _-]?)?(key|token)|expired|rejected the (key|token|request)|accepted the (key|token) but|scope/i,
    hint: "The platform refused the stored credentials. Reconnect the account, then retry.",
    action: SETTINGS,
  },
  {
    kind: "paused",
    test: /^paused:/i,
    hint: "Pulse paused this platform after repeated failures. It resumes on its own; retry now only if you've fixed the cause.",
  },
  {
    kind: "rate_limited",
    test: /\b429\b|rate.?limit|too many requests/i,
    hint: "The platform asked Pulse to slow down. It will retry after the limit lifts.",
  },
  {
    kind: "backing_off",
    test: /retrying in \d+s|— retrying\.?$/i,
    hint: "A temporary failure. Pulse will retry this automatically.",
  },
  {
    kind: "timeout",
    test: /timed out|took too long/i,
    hint: "The platform was slow to answer. Retrying usually works; check the platform first so it doesn't post twice.",
  },
  {
    kind: "needs_title",
    test: /requires a title|needs a title/i,
    hint: "Give the piece a title in the editor, then retry.",
  },
  {
    kind: "withdrawn",
    test: /archived before|moved back before/i,
    hint: "This was cancelled on purpose. Re-approve the piece to queue it again.",
  },
  {
    kind: "server",
    test: /\b5\d\d\b|bad gateway|service unavailable/i,
    hint: "The platform had a server error. It's usually temporary, so try again shortly.",
  },
];

export function explainPublishError(error) {
  if (!error || typeof error !== "string") return null;
  const rule = RULES.find((r) => r.test.test(error));
  if (!rule) return null;
  return { kind: rule.kind, hint: rule.hint, action: rule.action ?? null };
}
