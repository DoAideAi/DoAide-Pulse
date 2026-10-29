import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";
import { formatCount, formatRate, formatWhen } from "../../lib/format";
import { TRAFFIC_WINDOWS, searchShare } from "../../lib/seo";
import { ErrorBanner, SectionHeader, Skeleton, Stat } from "../ui/Bits";

const isWebLink = (url) => typeof url === "string" && /^https?:\/\//i.test(url);

/**
 * Which content brings people to the DoAide sites, from Umami — read by the
 * API, never by the browser. Pages a Pulse piece lives at are named and
 * linked to it; anything under a blog-like path counts as content too.
 */
export default function TrafficPanel() {
  const [days, setDays] = useState(30);
  const [refreshing, setRefreshing] = useState(false);
  const state = useApi(() => api.seoTraffic(days), [days]);

  async function refresh() {
    setRefreshing(true);
    try {
      state.setData(await api.seoTraffic(days, { refresh: true }));
      state.setError(null);
    } catch (err) {
      state.setError(err.message || String(err));
    } finally {
      setRefreshing(false);
    }
  }

  const data = state.data;
  const window = `last ${days} days`;
  const share = data
    ? searchShare({
        search_visits: data.totals.search_visits,
        referrers: data.sites.flatMap((s) => s.referrers || []),
      })
    : null;

  return (
    <section aria-label="Search traffic" className="space-y-8">
      <div className="flex flex-wrap items-center justify-end gap-3">
        <div className="flex gap-1" role="group" aria-label="Window">
          {TRAFFIC_WINDOWS.map((w) => (
            <button
              key={w}
              onClick={() => setDays(w)}
              aria-pressed={days === w}
              className={`min-h-[48px] rounded-md px-3 font-mono text-[11px] transition-colors ${
                days === w ? "bg-brand-50 text-brand-600" : "text-ink-400 hover:bg-ink-400/10 hover:text-ink-700"
              }`}
            >
              {w}d
            </button>
          ))}
        </div>
        <button className="btn-ghost" onClick={refresh} disabled={refreshing}>
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <ErrorBanner message={state.error} onRetry={refresh} />
      {!data && state.loading && <Skeleton rows={6} />}
      {data && (data.umami_error || !data.umami_configured) && (
        <p role="status" className="rounded-lg border border-warn/25 bg-warn-wash px-4 py-3 text-sm text-ink-700">
          {data.umami_error || "Umami is not configured."}
        </p>
      )}

      {data?.umami_configured && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Page views" value={formatCount(data.totals.pageviews)} hint={window} />
            <Stat label="Visitors" value={formatCount(data.totals.visitors)} hint={window} />
            <Stat label="From search" value={formatCount(data.totals.search_visits)} hint="referred visits" />
            <Stat label="Search share" value={formatRate(share, 0)} hint="of referred visits" />
          </div>

          <section aria-label="Content driving traffic" className="space-y-3">
            <SectionHeader title="Content driving traffic" subtitle={`Updated ${formatWhen(data.generated_at)}`} />
            {data.top_content.length === 0 ? (
              <p className="text-sm text-ink-500">
                No article pages in any site&apos;s top pages yet.{" "}
                <Link to="/seo?tab=posts" className="text-brand-600">Write an SEO post</Link>
              </p>
            ) : (
              <div className="panel overflow-x-auto">
                <table className="w-full min-w-[560px] text-sm">
                  <thead>
                    <tr className="border-b border-line text-left">
                      <th className="cell eyebrow">Page</th>
                      <th className="cell eyebrow">Site</th>
                      <th className="cell eyebrow text-right">Views</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {data.top_content.map((p) => (
                      <tr key={`${p.site_key}${p.path}`}>
                        <td className="cell">
                          {p.content_id ? (
                            <Link to={`/content/${p.content_id}`} className="font-medium text-ink-900 hover:text-brand-600">
                              {p.title}
                            </Link>
                          ) : isWebLink(p.url) ? (
                            <a href={p.url} target="_blank" rel="noopener noreferrer" className="font-mono text-xs text-ink-700 hover:text-brand-600">
                              {p.path}
                            </a>
                          ) : (
                            // Umami's collect endpoint takes any URL from
                            // anyone, so a reported "path" is not trusted to
                            // be one: anything but http(s) is text, never href.
                            <span className="font-mono text-xs text-ink-700">{p.path}</span>
                          )}
                        </td>
                        <td className="cell text-xs text-ink-500">{p.domain}</td>
                        <td className="cell text-right font-mono">{formatCount(p.views)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section aria-label="Traffic by site" className="space-y-3">
            <SectionHeader title="By site" />
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {data.sites.map((site) => (
                <SiteCard key={site.key} site={site} />
              ))}
            </div>
          </section>
        </>
      )}
    </section>
  );
}

function SiteCard({ site }) {
  return (
    <article className="panel space-y-3 px-5 py-4" aria-label={site.domain}>
      <header className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink-900">{site.domain}</h3>
        {site.status === "ok" && (
          <span className="font-mono text-xs text-ink-500">{formatCount(site.pageviews)} views</span>
        )}
      </header>
      {site.status !== "ok" ? (
        <p className="text-xs text-ink-500">{site.error || "No traffic data."}</p>
      ) : (
        <>
          <div>
            <p className="eyebrow mb-1">Top pages</p>
            <ul className="space-y-1 text-xs">
              {site.top_pages.slice(0, 6).map((p) => (
                <li key={p.path} className="flex justify-between gap-2">
                  <span className={`truncate ${p.is_content ? "text-ink-900" : "text-ink-500"}`} title={p.title || p.path}>
                    {p.title || p.path}
                  </span>
                  <span className="font-mono text-ink-700">{formatCount(p.views)}</span>
                </li>
              ))}
            </ul>
          </div>
          {site.referrers.length > 0 && (
            <div>
              <p className="eyebrow mb-1">Referrers</p>
              <ul className="space-y-1 text-xs">
                {site.referrers.slice(0, 5).map((r) => (
                  <li key={r.referrer} className="flex justify-between gap-2">
                    <span className={`truncate ${r.search ? "text-good" : "text-ink-500"}`}>
                      {r.referrer}
                      {r.search && <span className="sr-only"> (search)</span>}
                    </span>
                    <span className="font-mono text-ink-700">{formatCount(r.visits)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </article>
  );
}
