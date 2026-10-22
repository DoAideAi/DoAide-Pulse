/**
 * Pure helpers for the SEO page.
 *
 * Kept out of the components so the wording and arithmetic are tested on
 * their own, the way lib/productActivity.js is for the Products page.
 */

/** One sentence for where a site's sitemap stands, and how worried to be. */
export function sitemapState(site) {
  if (!site?.checked) return { tone: "idle", label: "Not checked yet" };
  if (site.fetch_error) return { tone: "bad", label: "Sitemap unreachable" };
  if (site.submit_status === "error") return { tone: "bad", label: "Submission failed" };
  if (site.submit_status === "unconfigured") return { tone: "warn", label: "Not submitted" };
  if (site.gsc_errors > 0) return { tone: "warn", label: `${site.gsc_errors} Google errors` };
  return { tone: "good", label: "Submitted" };
}

/** Badge classes for a tone. */
export function toneClass(tone) {
  switch (tone) {
    case "good":
      return "bg-good-wash text-good";
    case "warn":
      return "bg-warn-wash text-warn";
    case "bad":
      return "bg-bad-wash text-bad";
    default:
      return "text-ink-400";
  }
}

/**
 * Google's indexed count, or "—" when it did not report one. Google has
 * stopped filling `indexed` in for many properties and sends 0, which would
 * otherwise read as "nothing indexed".
 */
export function indexedLabel(site) {
  if (!site || site.gsc_indexed === null || site.gsc_indexed === undefined) return "—";
  if (site.gsc_indexed === 0 && site.gsc_submitted > 0) return "not reported";
  return String(site.gsc_indexed);
}

/** Sites with a problem first, then by name — the list is read top-down. */
export function sortSites(sites) {
  const rank = { bad: 0, warn: 1, idle: 2, good: 3 };
  return [...(sites || [])].sort(
    (a, b) =>
      rank[sitemapState(a).tone] - rank[sitemapState(b).tone] || a.name.localeCompare(b.name),
  );
}
