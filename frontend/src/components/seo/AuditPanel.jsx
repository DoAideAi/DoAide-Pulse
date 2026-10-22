import { useState } from "react";
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";
import { formatWhen } from "../../lib/format";
import { rankedCounts, shortPath, sortAudits } from "../../lib/seo";
import { ErrorBanner, SectionHeader, Skeleton } from "../ui/Bits";

/**
 * Titles, descriptions, canonicals and Open Graph tags across every DoAide
 * site: what is missing, too long, or shared between pages. The full sweep
 * runs weekly on the worker; "Scan" re-checks one site now.
 */
export default function AuditPanel() {
  const state = useApi(() => api.seoAudit(), []);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  async function scan(site) {
    setBusy(site || "all");
    setError(null);
    setNotice(null);
    try {
      const result = await api.runSeoAudit(site);
      if (result.queued) {
        setNotice("Every site is being audited in the background. Refresh in a few minutes.");
      } else {
        state.setData(result);
      }
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(null);
    }
  }

  const data = state.data;

  return (
    <section aria-label="Meta tag audit" className="space-y-4">
      <SectionHeader
        title="Meta tag audit"
        subtitle="The homepage and sitemap pages of each site, checked every Monday."
        action={
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={state.reload} disabled={busy !== null}>
              Refresh
            </button>
            <button className="btn-primary" onClick={() => scan(null)} disabled={busy !== null}>
              {busy === "all" ? "Queuing…" : "Audit all"}
            </button>
          </div>
        }
      />
      <ErrorBanner message={error || state.error} onRetry={state.reload} />
      {notice && (
        <p role="status" className="rounded-lg border border-line bg-canvas px-4 py-3 text-sm text-ink-700">
          {notice}
        </p>
      )}
      {!data && state.loading && <Skeleton rows={6} />}
      {data && (
        <div className="space-y-3">
          {sortAudits(data.sites).map((site) => (
            <SiteAudit
              key={site.key}
              site={site}
              labels={data.issue_labels}
              busy={busy}
              onScan={() => scan(site.key)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function SiteAudit({ site, labels, busy, onScan }) {
  const counts = rankedCounts(site.counts);
  const tone = !site.scanned_at
    ? "text-ink-400"
    : site.issue_count === 0
      ? "bg-good-wash text-good"
      : "bg-warn-wash text-warn";
  return (
    <details className="panel group" aria-label={site.domain}>
      <summary className="flex min-h-[48px] cursor-pointer list-none items-center gap-3 px-5 py-3">
        <span className="min-w-0 flex-1">
          <span className="block font-medium text-ink-900">{site.domain}</span>
          <span className="text-xs text-ink-400">
            {site.scanned_at
              ? `${site.pages_scanned} pages · ${formatWhen(site.scanned_at)}`
              : "Not audited yet"}
          </span>
        </span>
        <span className={`badge ${tone}`}>
          {site.scanned_at ? `${site.issue_count} issues` : "—"}
        </span>
        <button
          type="button"
          className="btn-quiet"
          onClick={(e) => {
            e.preventDefault();
            onScan();
          }}
          disabled={busy !== null}
          aria-label={`Audit ${site.domain}`}
        >
          {busy === site.key ? "Scanning…" : "Scan"}
        </button>
      </summary>

      <div className="space-y-4 border-t border-line px-5 py-4">
        {site.error && <p className="text-xs text-bad">{site.error}</p>}
        {counts.length > 0 && (
          <ul className="flex flex-wrap gap-2" aria-label="Issues by type">
            {counts.map(([code, n]) => (
              <li key={code} className="chip">
                {labels[code] || code} <span className="text-ink-400">×{n}</span>
              </li>
            ))}
          </ul>
        )}

        {["title", "description"].map((kind) =>
          site.duplicates?.[kind]?.length ? (
            <div key={kind}>
              <p className="eyebrow mb-1">Duplicate {kind}s</p>
              <ul className="space-y-2 text-xs">
                {site.duplicates[kind].map((group) => (
                  <li key={group.value}>
                    <p className="text-ink-700">“{group.value}”</p>
                    <p className="text-ink-400">
                      {group.urls.map((u) => shortPath(u, site.domain)).join(", ")}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          ) : null,
        )}

        {site.pages?.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-xs">
              <thead>
                <tr className="text-left">
                  <th className="cell eyebrow">Page</th>
                  <th className="cell eyebrow">Title</th>
                  <th className="cell eyebrow">Issues</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {site.pages.map((p) => (
                  <tr key={p.url}>
                    <td className="cell font-mono">
                      <a href={p.url} target="_blank" rel="noopener noreferrer" className="hover:text-brand-600">
                        {shortPath(p.url, site.domain)}
                      </a>
                    </td>
                    <td className="cell max-w-[240px] truncate text-ink-700" title={p.title || ""}>
                      {p.title || "—"}
                    </td>
                    <td className="cell">
                      {p.issues.length === 0 ? (
                        <span className="text-good">OK</span>
                      ) : (
                        <span className="text-ink-600">{p.issues.map((i) => labels[i] || i).join(" · ")}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </details>
  );
}
