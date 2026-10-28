// Which part of Pulse a page belongs to, for the feedback widget.
//
// Matched on the path rather than on the component that rendered it, because
// the path is what the router actually knows at the moment the widget opens —
// and it is the same answer on a page that failed to load, which is exactly
// when someone reaches for "Report a bug".

/** First match wins, so the more specific prefixes come first. */
const ROUTES = [
  [/^\/content\/[^/]+/, "Content Editor"],
  [/^\/content\/?$/, "Content Library"],
  [/^\/analytics/, "Analytics"],
  [/^\/(my-templates|templates)/, "Templates"],
  [/^\/calendar/, "Calendar"],
  [/^\/settings/, "Settings"],
  [/^\/publish/, "Publishing"],
  [/^\/dashboard/, "Dashboard"],
  [/^\/projects/, "Projects"],
  [/^\/triggers/, "Triggers"],
  [/^\/seo/, "SEO"],
  [/^\/products/, "Product Activity"],
  [/^\/tools\//, "Free Tools"],
  [/^\/blog/, "Blog"],
  [/^\/article\//, "Public Article"],
  [/^\/preview\//, "Preview Link"],
  [/^\/gallery/, "Newsletter Gallery"],
  [/^\/admin\/feedback/, "Feedback Admin"],
  [/^\/login/, "Sign In"],
  [/^\/$/, "Landing Page"],
];

export const OTHER_AREA = "Other";

/**
 * Every area a person can choose in the widget. Translations has no route of
 * its own — it is a panel inside the editor — so it can only be chosen, never
 * detected, which is the reason the choice exists.
 */
export const FEATURE_AREAS = [
  ...new Set([...ROUTES.map(([, label]) => label), "Translations", OTHER_AREA]),
];

/** The feature area for *pathname*, or "Other" for a path no rule names. */
export function featureFor(pathname) {
  const path = pathname || "/";
  const hit = ROUTES.find(([pattern]) => pattern.test(path));
  return hit ? hit[1] : OTHER_AREA;
}

/**
 * A short, readable browser description from a user agent string — shown in
 * the widget so the person can see what is being sent. The full string is
 * what the server records, from the request itself.
 */
export function describeBrowser(userAgent) {
  const ua = userAgent || "";
  const browser =
    (/Edg\//.test(ua) && "Edge") ||
    (/Firefox\//.test(ua) && "Firefox") ||
    (/Chrome\//.test(ua) && "Chrome") ||
    (/Safari\//.test(ua) && "Safari") ||
    "Unknown browser";
  const os =
    (/iPhone|iPad/.test(ua) && "iOS") ||
    (/Android/.test(ua) && "Android") ||
    (/Mac OS X/.test(ua) && "macOS") ||
    (/Windows/.test(ua) && "Windows") ||
    (/Linux/.test(ua) && "Linux") ||
    "";
  return os ? `${browser} on ${os}` : browser;
}
