import { Link } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";
import { formatCount, formatDateTime, formatWhen } from "../../lib/format";
import {
  browserZone,
  calendarWeeks,
  indexedLabel,
  postLabel,
  postTone,
  sitemapState,
  sortSites,
  toneClass,
} from "../../lib/seo";
import { ErrorBanner, SectionHeader, Skeleton, Stat } from "../ui/Bits";
import { MultiLineChart } from "../ui/Charts";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/**
 * Where every DoAide site stands in search, from what Pulse has already
 * stored: sitemap state and Google's counts, SEO posts per product, and a
 * calendar of what went out and what is queued.
 */
export default function HealthPanel() {
  const state = useApi(() => api.seoHealth(browserZone()), []);
  const history = useApi(() => api.seoHealthHistory(90), []);
  const data = state.data;

  return (
    <div className="space-y-8">
      <ErrorBanner message={state.error} onRetry={state.reload} />
      {!data && state.loading && <Skeleton rows={6} />}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Stat
              label="Sitemaps submitted"
              value={`${data.totals.sitemaps_submitted}/${data.totals.sites}`}
              hint={data.totals.sitemap_problems ? `${data.totals.sitemap_problems} with problems` : "no problems"}
            />
            <Stat label="URLs in sitemaps" value={formatCount(data.totals.urls_in_sitemaps)} hint="all sites" />
            <Stat label="Indexed pages" value={formatCount(data.totals.indexed_pages)} hint="as Google reports" />
            <Stat
              label="SEO posts"
              value={formatCount(data.totals.posts_published_30d)}
              hint={`last 30 days · ${data.totals.posts_scheduled} scheduled`}
            />
            <Stat label="Meta tag issues" value={formatCount(data.totals.meta_issues)} hint="latest audit" />
          </div>

          <HealthOverTime history={history} />

          <section aria-label="Sites" className="space-y-3">
            <SectionHeader title="By site" subtitle={`Updated ${formatWhen(data.generated_at)}`} />
            <div className="panel overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-line text-left">
                    <th className="cell eyebrow">Site</th>
                    <th className="cell eyebrow">Sitemap</th>
                    <th className="cell eyebrow text-right">URLs</th>
                    <th className="cell eyebrow text-right">Indexed</th>
                    <th className="cell eyebrow text-right">Posts 30d</th>
                    <th className="cell eyebrow text-right">Scheduled</th>
                    <th className="cell eyebrow text-right">Meta issues</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {sortSites(data.sites).map((site) => {
                    const s = sitemapState(site);
                    return (
                      <tr key={site.key}>
                        <td className="cell">
                          <a href={site.url} target="_blank" rel="noopener noreferrer" className="font-medium text-ink-900 hover:text-brand-600">
                            {site.domain}
                          </a>
                        </td>
                        <td className="cell">
                          <span className={`badge ${toneClass(s.tone)}`}>{s.label}</span>
                        </td>
                        <td className="cell text-right font-mono">{site.url_count ?? "—"}</td>
                        <td className="cell text-right font-mono">{indexedLabel(site)}</td>
                        <td className="cell text-right font-mono">{site.recent_posts}</td>
                        <td className="cell text-right font-mono">{site.scheduled_posts}</td>
                        <td className="cell text-right font-mono">
                          <Link to="/seo?tab=audit" className="hover:text-brand-600">
                            {site.meta_issues ?? "—"}
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-ink-400">
              Posts count towards a site when their project&apos;s live URL is on that site.
            </p>
          </section>

          <ContentCalendar days={data.calendar} />

          <section aria-label="Recent SEO posts" className="space-y-3">
            <SectionHeader title="Recent posts" />
            {data.recent_posts.length === 0 ? (
              <p className="text-sm text-ink-500">
                Nothing published yet. <Link to="/seo?tab=posts" className="text-brand-600">Write an SEO post</Link>
              </p>
            ) : (
              <ul className="panel divide-y divide-line">
                {data.recent_posts.map((p) => (
                  <li key={p.id} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                    <Link to={`/content/${p.id}`} className="min-w-0 flex-1 truncate font-medium text-ink-900 hover:text-brand-600">
                      {p.title}
                    </Link>
                    {p.focus_keyword && <span className="hidden font-mono text-xs text-ink-400 sm:inline">{p.focus_keyword}</span>}
                    <time className="shrink-0 text-xs text-ink-400" dateTime={p.published_at}>
                      {formatDateTime(p.published_at)}
                    </time>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}

/**
 * How the estate's footing moved: one point per day, written nightly and by
 * every sweep. Two charts rather than one — URL counts live in the hundreds
 * while problems live near zero, and one shared scale would flatten the line
 * that matters into the baseline.
 */
function HealthOverTime({ history }) {
  const points = history.data?.points ?? [];
  return (
    <section aria-label="Health over time" className="space-y-3">
      <SectionHeader
        title="Health over time"
        subtitle="Daily snapshots, last 90 days. New points appear nightly and after each sweep."
      />
      <ErrorBanner message={history.error} onRetry={history.reload} />
      {history.loading && !history.data && <Skeleton rows={3} />}
      {history.data && points.length < 2 && (
        <p className="rounded-lg border border-line bg-canvas px-4 py-3 text-sm text-ink-500">
          Not enough snapshots yet — the chart starts drawing after two days of data.
        </p>
      )}
      {points.length >= 2 && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="panel p-5">
            <h3 className="mb-3 text-sm font-semibold text-ink-900">Pages in search</h3>
            <MultiLineChart
              label="Pages in search"
              series={[
                {
                  key: "urls",
                  label: "URLs in sitemaps",
                  points: points.map((p) => ({ label: p.date, value: p.urls_in_sitemaps })),
                },
                {
                  key: "indexed",
                  label: "Indexed (Google)",
                  points: points.map((p) => ({ label: p.date, value: p.indexed_pages })),
                },
              ]}
              formatValue={formatCount}
            />
          </div>
          <div className="panel p-5">
            <h3 className="mb-3 text-sm font-semibold text-ink-900">Problems</h3>
            <MultiLineChart
              label="Problems"
              series={[
                {
                  key: "meta",
                  label: "Meta tag issues",
                  points: points.map((p) => ({ label: p.date, value: p.meta_issues })),
                },
                {
                  key: "sitemap",
                  label: "Sitemap problems",
                  points: points.map((p) => ({ label: p.date, value: p.sitemap_problems })),
                },
              ]}
              formatValue={formatCount}
              emptyHint="No problems recorded in this window — as it should be."
            />
          </div>
        </div>
      )}
    </section>
  );
}

function ContentCalendar({ days }) {
  const today = new Date().toISOString().slice(0, 10);
  return (
    <section aria-label="Content calendar" className="space-y-3">
      <SectionHeader title="Content calendar" subtitle="SEO posts, last week and the next four." />
      <div className="panel overflow-x-auto p-3">
        <div className="grid min-w-[640px] grid-cols-7 gap-1">
          {WEEKDAYS.map((d) => (
            <div key={d} className="eyebrow px-1 pb-1">
              {d}
            </div>
          ))}
          {calendarWeeks(days).flat().map((day, i) =>
            day ? (
              <div
                key={day.date}
                className={`min-h-[72px] rounded-md border p-1.5 ${
                  day.date === today ? "border-brand-500" : "border-line"
                }`}
                data-date={day.date}
              >
                <p className="font-mono text-[10px] text-ink-400">{Number(day.date.slice(8))}</p>
                <ul className="mt-1 space-y-1">
                  {day.posts.map((entry) => {
                    const p = { ...entry, scheduled_for: entry.when };
                    return (
                      <li key={p.id}>
                        <Link
                          to={`/content/${p.id}`}
                          title={`${p.title} — ${postLabel(p)}`}
                          className={`block truncate rounded px-1 py-0.5 text-[11px] ${toneClass(postTone(p))}`}
                        >
                          {p.title}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : (
              <div key={`pad-${i}`} aria-hidden="true" />
            ),
          )}
        </div>
      </div>
    </section>
  );
}
