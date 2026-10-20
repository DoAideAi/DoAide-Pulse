import { useCallback, useEffect, useState } from "react";
import { SectionBoundary } from "../components/ErrorBoundary";
import { ErrorBanner, SectionHeader, Skeleton, Stat } from "../components/ui/Bits";
import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import { formatCount, formatRate, formatWhen } from "../lib/format";
import {
  AUTO_REFRESH_MS,
  PRODUCT_WINDOWS,
  averageVisitSeconds,
  bounceRate,
  formatSeconds,
  sortProducts,
  umamiNotice,
} from "../lib/productActivity";

/**
 * What people are doing across every DoAide product.
 *
 * One request: the API reads Umami server-side (its credentials never reach
 * the browser) and joins the signups, logins and key actions the products
 * reported. Re-asked every minute while the tab is visible — the server
 * caches Umami for the same minute, so that costs nothing extra — and the
 * Refresh button skips that cache.
 */
export default function ProductActivity() {
  const [days, setDays] = useState(7);
  const [auto, setAuto] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const dash = useApi(() => api.productActivity(days), [days]);
  const { reload, setData, setError } = dash;

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      setData(await api.productActivity(days, { refresh: true }));
      setError(null);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setRefreshing(false);
    }
  }, [days, setData, setError]);

  useEffect(() => {
    if (!auto) return undefined;
    const id = setInterval(() => {
      if (typeof document === "undefined" || document.visibilityState !== "hidden") reload();
    }, AUTO_REFRESH_MS);
    return () => clearInterval(id);
  }, [auto, reload]);

  const data = dash.data;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="page-title">Products</h1>
          <p className="mt-1 text-sm text-ink-500">
            Traffic, signups and key actions across every DoAide product.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex gap-1" role="group" aria-label="Window">
            {PRODUCT_WINDOWS.map((w) => (
              <button
                key={w}
                onClick={() => setDays(w)}
                aria-pressed={days === w}
                className={`rounded-md px-2 py-1 font-mono text-[11px] transition-colors ${
                  days === w
                    ? "bg-brand-50 text-brand-600"
                    : "text-ink-400 hover:bg-ink-400/10 hover:text-ink-700"
                }`}
              >
                {w === 1 ? "24h" : `${w}d`}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1.5 text-xs text-ink-500">
            <input
              type="checkbox"
              checked={auto}
              onChange={(e) => setAuto(e.target.checked)}
            />
            Auto-refresh
          </label>
          <button className="btn-ghost" onClick={refresh} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {dash.error && <ErrorBanner message={dash.error} onRetry={refresh} />}

      {!data && dash.loading && <Skeleton rows={6} />}

      {data && (
        <>
          {data.umami_error && (
            <p role="status" className="rounded-lg border border-warn/25 bg-warn-wash px-4 py-3 text-sm text-ink-700">
              {data.umami_error}
            </p>
          )}

          <Totals totals={data.totals} days={data.days} />

          <SectionBoundary name="products:cards">
            <section aria-label="Products">
              <SectionHeader
                title="By product"
                subtitle={`Updated ${formatWhen(data.generated_at)}`}
              />
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {sortProducts(data.products).map((p) => (
                  <ProductCard key={p.key} product={p} />
                ))}
              </div>
            </section>
          </SectionBoundary>

          <SectionBoundary name="products:recent">
            <RecentFeed rows={data.recent} />
          </SectionBoundary>
        </>
      )}
    </div>
  );
}

function Totals({ totals, days }) {
  const window = days === 1 ? "last 24h" : `last ${days} days`;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <Stat label="Active now" value={formatCount(totals.active_now)} hint="all products" />
      <Stat label="Page views" value={formatCount(totals.pageviews)} hint={window} />
      <Stat label="Visitors" value={formatCount(totals.visitors)} hint={window} />
      <Stat label="Signups" value={formatCount(totals.signups)} hint={window} />
      <Stat label="Logins" value={formatCount(totals.logins)} hint={window} />
    </div>
  );
}

function ProductCard({ product }) {
  const u = product.umami;
  const notice = umamiNotice(u);
  return (
    <article className="panel flex flex-col gap-4 px-5 py-4" aria-label={product.name}>
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-ink-900">{product.name}</h3>
          <a
            href={product.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-ink-400 hover:text-brand-600"
          >
            {product.domain}
          </a>
        </div>
        {u.status === "ok" && (
          <span
            className={`badge ${u.active_now > 0 ? "bg-good-wash text-good" : "text-ink-400"}`}
            aria-label={`${u.active_now} active now`}
          >
            {u.active_now} live
          </span>
        )}
      </header>

      {notice ? (
        <p className="text-xs text-ink-500">{notice}</p>
      ) : (
        <dl className="grid grid-cols-3 gap-2 text-center">
          <Figure label="Views" value={formatCount(u.pageviews)} />
          <Figure label="Visitors" value={formatCount(u.visitors)} />
          <Figure label="Visits" value={formatCount(u.visits)} />
          <Figure label="Bounce" value={formatRate(bounceRate(u), 0)} />
          <Figure label="Avg visit" value={formatSeconds(averageVisitSeconds(u))} />
          <Figure label="Signups" value={formatCount(product.signups)} />
        </dl>
      )}

      <div>
        <p className="eyebrow mb-1.5">Key actions</p>
        <ul className="space-y-1 text-sm">
          {product.key_actions.map((a) => (
            <li key={a.label} className="flex justify-between gap-2" title={a.events.join(", ")}>
              <span className="text-ink-600">{a.label}</span>
              <span className="font-mono text-ink-900">{formatCount(a.count)}</span>
            </li>
          ))}
          <li className="flex justify-between gap-2">
            <span className="text-ink-600">Logins</span>
            <span className="font-mono text-ink-900">{formatCount(product.logins)}</span>
          </li>
        </ul>
      </div>

      {u.top_pages?.length > 0 && (
        <div>
          <p className="eyebrow mb-1.5">Top pages</p>
          <ul className="space-y-1 text-xs">
            {u.top_pages.map((page) => (
              <li key={page.name} className="flex justify-between gap-2">
                <span className="truncate text-ink-500">{page.name}</span>
                <span className="font-mono text-ink-700">{formatCount(page.count)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}

function Figure({ label, value }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-ink-400">{label}</dt>
      <dd className="font-mono text-sm text-ink-900">{value}</dd>
    </div>
  );
}

function RecentFeed({ rows }) {
  return (
    <section aria-label="Recent signups and logins" className="panel">
      <div className="px-5 pt-4">
        <SectionHeader
          title="Recent signups and logins"
          subtitle="Reported by each product's backend. Emails are masked before Pulse stores them."
        />
      </div>
      {rows.length === 0 ? (
        <p className="px-5 pb-5 text-sm text-ink-500">
          Nothing reported yet. Products send these to{" "}
          <code className="font-mono text-xs">POST /api/v1/products/events</code> with the
          ingest token.
        </p>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((r, i) => (
            <li key={`${r.occurred_at}-${i}`} className="flex items-center gap-3 px-5 py-2.5 text-sm">
              <span
                className={`badge ${r.kind === "signup" ? "bg-good-wash text-good" : "text-ink-500"}`}
              >
                {r.kind === "signup" ? "Signup" : "Login"}
              </span>
              <span className="w-28 shrink-0 font-medium text-ink-900">{r.product_name}</span>
              <span className="min-w-0 flex-1 truncate text-ink-500">{r.actor || "—"}</span>
              <time className="shrink-0 text-xs text-ink-400" dateTime={r.occurred_at}>
                {formatWhen(r.occurred_at)}
              </time>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
