/**
 * Pure helpers for the cross-product activity page.
 *
 * Kept out of the component so the arithmetic (and its "—" for an unknown) is
 * tested on its own, the way lib/analytics.js is for the Analytics page.
 */

/** Windows the page offers. The API accepts 1..90. */
export const PRODUCT_WINDOWS = [1, 7, 30];

/** How often the page re-asks while it is visible. Matches the server cache. */
export const AUTO_REFRESH_MS = 60_000;

/** Bounces over visits as a 0..1 rate, or null when there were no visits. */
export function bounceRate(umami) {
  if (!umami || !umami.visits) return null;
  return Math.min(1, umami.bounces / umami.visits);
}

/**
 * Average visit length in seconds, or null. Umami's `totaltime` is the sum of
 * visit durations in seconds over the window.
 */
export function averageVisitSeconds(umami) {
  if (!umami || !umami.visits) return null;
  return Math.round(umami.totaltime / umami.visits);
}

/** "42s", "3m 05s", or "—". */
export function formatSeconds(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return `${m}m ${s}s`;
}

/**
 * What a card says instead of numbers when Umami had none for it. Null when
 * the numbers are there.
 */
export function umamiNotice(umami) {
  switch (umami?.status) {
    case "ok":
      return null;
    case "unconfigured":
      return "Umami not configured on the server.";
    case "not_found":
      return "No Umami site found for this domain.";
    case "error":
      return `Umami error: ${umami.error || "unknown"}`;
    default:
      return "No traffic data.";
  }
}

/**
 * Cards ordered by what is happening now: live visitors, then page views, so
 * the product with people on it right now is the first one read. Products with
 * no Umami data keep their catalog order at the end.
 */
export function sortProducts(products) {
  const live = (p) => (p.umami?.status === "ok" ? 1 : 0);
  return [...(products || [])]
    .map((p, i) => ({ p, i }))
    .sort(
      (a, b) =>
        live(b.p) - live(a.p) ||
        (b.p.umami?.active_now || 0) - (a.p.umami?.active_now || 0) ||
        (b.p.umami?.pageviews || 0) - (a.p.umami?.pageviews || 0) ||
        a.i - b.i,
    )
    .map(({ p }) => p);
}
