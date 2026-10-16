import { useState } from "react";
import { ErrorBanner, SectionHeader, Skeleton, Stat } from "../ui/Bits";
import { BarRow } from "../ui/Charts";
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";
import { formatCount, formatRate, titleize } from "../../lib/format";

/**
 * Where every piece and every publication stands: content by status, and how
 * often a publish attempt actually landed, overall and per platform.
 *
 * The reach panels on this page describe what got out; this describes how much
 * did. It renders even before anything has been published — a run of failed
 * publications is exactly when there are no views to show, and exactly when
 * this panel is the one worth reading.
 */
export function PipelineHealth() {
  const { data, error, loading, reload } = useApi(() => api.pipeline(), []);

  if (loading && !data) return <Skeleton rows={2} />;
  if (error) return <ErrorBanner message={error} onRetry={reload} />;

  const { content_by_status: statuses, publications, by_platform: platforms } = data;
  const settled = publications.published + publications.failed;
  const maxStatus = Math.max(...statuses.map((row) => row.count), 0);

  return (
    <section>
      <SectionHeader
        title="Pipeline health"
        subtitle="How much of the writing made it out, and where it got stuck."
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Publish success"
          value={formatRate(publications.success_rate)}
          hint={
            settled === 0
              ? "nothing has settled yet"
              : `${formatCount(publications.published)} of ${formatCount(settled)} attempts`
          }
        />
        <Stat label="Published" value={formatCount(publications.published)} />
        <Stat label="Failed" value={formatCount(publications.failed)} />
        <Stat
          label="In flight"
          value={formatCount(publications.in_flight)}
          hint="queued, scheduled or sending"
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-medium text-ink-700">Content by status</h3>
          <div className="panel divide-y divide-line">
            {statuses.map((row) => (
              <BarRow
                key={row.status}
                label={titleize(row.status)}
                value={row.count}
                max={maxStatus}
                display={formatCount(row.count)}
                tone={row.status === "failed" ? "muted" : "brand"}
              />
            ))}
          </div>
        </div>
        <div>
          <h3 className="mb-2 text-sm font-medium text-ink-700">Success rate by platform</h3>
          <div className="panel">
            {platforms.length === 0 ? (
              <p className="px-5 py-6 text-sm text-ink-500">
                Nothing has been sent to a platform yet.
              </p>
            ) : (
              <div className="divide-y divide-line">
                {platforms.map((row) => (
                  <BarRow
                    key={row.platform}
                    label={titleize(row.platform)}
                    // The bar is the success rate, so an unsettled platform
                    // shows an empty bar and a dash rather than a zero.
                    value={row.success_rate ?? 0}
                    max={1}
                    display={formatRate(row.success_rate)}
                    tone={row.failed > 0 ? "muted" : "brand"}
                    hint={[
                      `${formatCount(row.published)} published`,
                      row.failed > 0 ? `${formatCount(row.failed)} failed` : null,
                      row.in_flight > 0 ? `${formatCount(row.in_flight)} in flight` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

const ACTIVITY_WINDOWS = [7, 30, 90];

/** Pages opened and actions taken in Pulse itself, from the activity tracker. */
export function ActivityPanel() {
  const [days, setDays] = useState(30);
  const { data, error, loading, reload } = useApi(() => api.activitySummary(days), [days]);

  const picker = (
    <div className="flex shrink-0 gap-1" role="group" aria-label="Activity window">
      {ACTIVITY_WINDOWS.map((value) => (
        <button
          key={value}
          type="button"
          className={`rounded-md px-2 py-1 font-mono text-[11px] transition-colors ${
            value === days
              ? "bg-brand-50 text-brand-600"
              : "text-ink-400 hover:bg-ink-400/10 hover:text-ink-700"
          }`}
          aria-pressed={value === days}
          onClick={() => setDays(value)}
        >
          {value}d
        </button>
      ))}
    </div>
  );

  let body;
  if (loading && !data) body = <Skeleton rows={2} />;
  else if (error) body = <ErrorBanner message={error} onRetry={reload} />;
  else if (data.page_views + data.actions === 0) {
    body = (
      <p className="panel px-5 py-6 text-sm text-ink-500">
        No activity recorded in the last {days} days.
      </p>
    );
  } else {
    body = (
      <div className="grid gap-6 lg:grid-cols-2">
        <CountList
          title={`Most-visited pages · ${formatCount(data.page_views)} views`}
          rows={data.top_pages}
        />
        <CountList
          title={`Most-taken actions · ${formatCount(data.actions)} actions`}
          rows={data.top_actions}
        />
      </div>
    );
  }

  return (
    <section>
      <SectionHeader
        title="Your activity"
        subtitle="What you opened and did in Pulse."
        action={picker}
      />
      {body}
    </section>
  );
}

function CountList({ title, rows }) {
  const max = Math.max(...rows.map((row) => row.count), 0);
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium text-ink-700">{title}</h3>
      <div className="panel divide-y divide-line">
        {rows.length === 0 ? (
          <p className="px-5 py-6 text-sm text-ink-500">None yet.</p>
        ) : (
          rows.map((row) => (
            <BarRow
              key={row.name}
              label={row.name}
              value={row.count}
              max={max}
              display={formatCount(row.count)}
            />
          ))
        )}
      </div>
    </div>
  );
}
