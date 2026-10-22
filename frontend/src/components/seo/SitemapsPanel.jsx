import { useState } from "react";
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";
import { formatCount, formatWhen } from "../../lib/format";
import { indexedLabel, sitemapState, sortSites, toneClass } from "../../lib/seo";
import { ErrorBanner, SectionHeader, Skeleton } from "../ui/Bits";

/**
 * Every DoAide site's sitemap: whether Pulse could fetch it, how many URLs it
 * lists, and what Search Console says about it. Submitting runs on the server
 * (weekly on its own); the buttons here are for "I just shipped pages".
 */
export default function SitemapsPanel() {
  const state = useApi(() => api.seoSitemaps(), []);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  async function submit(site) {
    setBusy(site || "all");
    setError(null);
    try {
      state.setData(await api.submitSitemaps(site));
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(null);
    }
  }

  const data = state.data;

  return (
    <section aria-label="Sitemaps" className="space-y-4">
      <SectionHeader
        title="Sitemaps"
        subtitle="Fetched by Pulse and submitted to Google Search Console every Monday."
        action={
          <button className="btn-primary" onClick={() => submit(null)} disabled={busy !== null}>
            {busy === "all" ? "Submitting…" : "Submit all"}
          </button>
        }
      />
      <ErrorBanner message={error || state.error} onRetry={state.reload} />
      {!data && state.loading && <Skeleton rows={6} />}
      {data && !data.gsc_configured && (
        <p role="status" className="rounded-lg border border-warn/25 bg-warn-wash px-4 py-3 text-sm text-ink-700">
          No Search Console service account is configured, so sitemaps are checked but not
          submitted. Set <code className="font-mono text-xs">GSC_SERVICE_ACCOUNT_FILE</code> on
          the server and add the account as an Owner of each property.
        </p>
      )}
      {data?.gsc_account && (
        <p className="text-xs text-ink-500">
          Submitting as <span className="font-mono">{data.gsc_account}</span> — it must be an
          Owner of each property in Search Console.
        </p>
      )}
      {data && (
        <div className="panel overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-line text-left">
                <th className="cell eyebrow">Site</th>
                <th className="cell eyebrow">Status</th>
                <th className="cell eyebrow text-right">URLs</th>
                <th className="cell eyebrow text-right">Indexed</th>
                <th className="cell eyebrow">Checked</th>
                <th className="cell" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {sortSites(data.sites).map((site) => {
                const s = sitemapState(site);
                const problem = site.fetch_error || site.submit_error;
                return (
                  <tr key={site.key}>
                    <td className="cell">
                      <a
                        href={site.sitemap_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-medium text-ink-900 hover:text-brand-600"
                      >
                        {site.domain}
                      </a>
                      {problem && <p className="mt-0.5 text-xs text-bad">{problem}</p>}
                    </td>
                    <td className="cell">
                      <span className={`badge ${toneClass(s.tone)}`}>{s.label}</span>
                    </td>
                    <td className="cell text-right font-mono">
                      {site.url_count === null ? "—" : formatCount(site.url_count)}
                    </td>
                    <td className="cell text-right font-mono">{indexedLabel(site)}</td>
                    <td className="cell text-xs text-ink-500">
                      {site.checked_at ? formatWhen(site.checked_at) : "never"}
                    </td>
                    <td className="cell text-right">
                      <button
                        className="btn-quiet"
                        onClick={() => submit(site.key)}
                        disabled={busy !== null}
                        aria-label={`Submit ${site.domain}`}
                      >
                        {busy === site.key ? "…" : "Submit"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
