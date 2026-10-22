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

/** The meta description length Google shows without truncating. */
export const META_MIN = 120;
export const META_MAX = 155;

/** How a meta description's length reads, as a tone and a hint. */
export function metaLengthHint(text) {
  const n = (text || "").trim().length;
  if (n === 0) return { tone: "idle", hint: `Aim for ${META_MIN}–${META_MAX} characters.` };
  if (n < META_MIN) return { tone: "warn", hint: `${n} characters — a little short.` };
  if (n > META_MAX) return { tone: "warn", hint: `${n} characters — Google will cut it off.` };
  return { tone: "good", hint: `${n} characters — good length.` };
}

/** "gst, input tax credit ,, itr" → ["gst", "input tax credit", "itr"], deduplicated. */
export function parseKeywords(text) {
  const seen = new Set();
  const out = [];
  for (const raw of (text || "").split(",")) {
    const k = raw.trim();
    if (k && !seen.has(k.toLowerCase())) {
      seen.add(k.toLowerCase());
      out.push(k);
    }
  }
  return out;
}

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Add a link to the body. The first plain mention of the anchor text becomes
 * the link — that is where a reader expects it — and a mention already inside
 * a link or a heading is left alone. With no mention, it goes at the end
 * under "Related".
 */
export function insertLink(body, anchor, url) {
  const text = body || "";
  const lines = text.split("\n");
  const pattern = new RegExp(`(^|[^\\w\\[/-])(${escapeRegExp(anchor)})(?![\\w\\]-])`, "i");
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (line.startsWith("#")) continue;
    const match = pattern.exec(line);
    if (!match) continue;
    // Inside an existing [text](url)? Count unclosed brackets before it.
    const before = line.slice(0, match.index + match[1].length);
    if ((before.match(/\[/g) || []).length > (before.match(/\]/g) || []).length) continue;
    if ((before.match(/\(/g) || []).length > (before.match(/\)/g) || []).length) continue;
    lines[i] =
      before + `[${match[2]}](${url})` + line.slice(match.index + match[0].length);
    return lines.join("\n");
  }
  const tail = text.trimEnd();
  const sep = tail ? "\n\n" : "";
  return `${tail}${sep}Related: [${anchor}](${url})\n`;
}

/** Badge tone for a post's status in the queue. */
export function postTone(post) {
  if (post.published_at || post.status === "published") return "good";
  if (post.status === "failed") return "bad";
  if (post.scheduled_for) return "warn";
  return "idle";
}

/** "Scheduled", "Published", "Draft"… for the queue. */
export function postLabel(post) {
  if (post.published_at || post.status === "published") return "Published";
  if (post.status === "failed") return "Failed";
  if (post.scheduled_for) return "Scheduled";
  return post.status === "draft" ? "Draft" : post.status.charAt(0).toUpperCase() + post.status.slice(1);
}

/**
 * Lay the API's run of days out as week rows starting on Monday, padding the
 * first row with nulls so each date sits under its weekday.
 */
export function calendarWeeks(days) {
  if (!days?.length) return [];
  const first = new Date(`${days[0].date}T00:00:00`);
  const lead = (first.getDay() + 6) % 7; // Monday = 0
  const cells = [...Array(lead).fill(null), ...days];
  const weeks = [];
  for (let i = 0; i < cells.length; i += 7) {
    const week = cells.slice(i, i + 7);
    while (week.length < 7) week.push(null);
    weeks.push(week);
  }
  return weeks;
}

/** The browser's IANA zone, for the calendar's day boundaries. */
export function browserZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}
