import { useState } from "react";
import { Empty, ErrorBanner, Skeleton } from "../components/ui/Bits";
import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import { formatDateTime } from "../lib/format";

const CATEGORY_LABELS = {
  bug: "Bug Report",
  feature: "Feature Request",
  general: "General Feedback",
  other: "Other",
};

/**
 * Everything left through the feedback widget, newest first.
 *
 * The install's operator only — the API refuses everyone else with a 403, and
 * this page says so rather than showing an empty list, which would read as "no
 * feedback yet" to the one person who is not allowed to know.
 */
export default function AdminFeedback() {
  const [category, setCategory] = useState("");
  const [feature, setFeature] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");

  const list = useApi(
    () => api.listFeedback({ category, feature, since, until, limit: 200 }),
    [category, feature, since, until],
  );
  const features = useApi(() => api.feedbackFeatures(), []);

  if (list.errorStatus === 403 || features.errorStatus === 403) {
    return (
      <div className="space-y-4">
        <h1 className="page-title">Feedback</h1>
        <ErrorBanner message="Feedback is readable by this install's operator only." />
      </div>
    );
  }

  const rows = list.data ?? [];
  const filtered = Boolean(category || feature || since || until);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Feedback</h1>
        <p className="mt-1 text-sm text-ink-500">
          Left through the Feedback button, by signed-in users and visitors alike.
        </p>
      </div>

      <div className="panel grid gap-3 p-4 sm:grid-cols-4">
        <div>
          <label className="label" htmlFor="af-category">Category</label>
          <select
            id="af-category"
            className="input"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">All categories</option>
            {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="af-feature">Feature</label>
          <select
            id="af-feature"
            className="input"
            value={feature}
            onChange={(e) => setFeature(e.target.value)}
          >
            <option value="">All features</option>
            {(features.data ?? []).map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="af-since">From</label>
          <input
            id="af-since"
            className="input"
            type="date"
            value={since}
            max={until || undefined}
            onChange={(e) => setSince(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="af-until">To</label>
          <input
            id="af-until"
            className="input"
            type="date"
            value={until}
            min={since || undefined}
            onChange={(e) => setUntil(e.target.value)}
          />
        </div>
      </div>

      {list.error && !list.data && (
        <ErrorBanner message={`Could not load feedback: ${list.error}`} onRetry={list.reload} />
      )}
      {list.loading && !list.data && <Skeleton rows={4} />}
      {list.data && rows.length === 0 && (
        <Empty
          title={filtered ? "No feedback matches these filters" : "No feedback yet"}
          hint={filtered ? "Widen the filters to see more." : "It will appear here as people send it."}
        />
      )}

      {rows.length > 0 && (
        <ul className="space-y-3" aria-label="Feedback">
          {rows.map((row) => (
            <li key={row.id} className="panel p-4">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded-full bg-ink-50 px-2 py-0.5 font-medium text-ink-700">
                  {CATEGORY_LABELS[row.category] ?? row.category}
                </span>
                {row.detected_feature && (
                  <span className="rounded-full px-2 py-0.5 font-medium text-white" style={{ backgroundColor: "#2563eb" }}>
                    {row.detected_feature}
                  </span>
                )}
                <span className="text-ink-400">{formatDateTime(row.created_at)}</span>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm text-ink-900">{row.message}</p>
              <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs text-ink-500 sm:grid-cols-[auto_1fr]">
                {row.email && (
                  <>
                    <dt className="font-medium">Email</dt>
                    <dd><a className="text-brand-500 hover:underline" href={`mailto:${row.email}`}>{row.email}</a></dd>
                  </>
                )}
                {row.page_url && (
                  <>
                    <dt className="font-medium">Page</dt>
                    <dd className="font-mono">{row.page_url}</dd>
                  </>
                )}
                {row.user_agent && (
                  <>
                    <dt className="font-medium">Browser</dt>
                    <dd className="break-all">{row.user_agent}</dd>
                  </>
                )}
              </dl>
            </li>
          ))}
        </ul>
      )}
      {rows.length === 200 && (
        <p className="text-xs text-ink-400">Showing the newest 200. Narrow the filters to see older feedback.</p>
      )}
    </div>
  );
}
