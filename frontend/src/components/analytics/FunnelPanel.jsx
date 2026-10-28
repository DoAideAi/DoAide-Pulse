import { Link } from "react-router-dom";
import { ErrorBanner, SectionHeader, Skeleton, Stat } from "../ui/Bits";
import { BarRow } from "../ui/Charts";
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";
import { formatCount, formatRate, titleize } from "../../lib/format";

const DAYS = 90;
const STALE_DAYS = 7;

/** Where a piece came from, as the funnel's origins name it. */
const ORIGIN_LABELS = {
  manual: "Written by hand",
  autopilot: "Autopilot",
  trigger: "Triggers",
  template: "Templates",
  idea: "Ideas",
  api: "API",
  other: "Other",
};

export function originLabel(origin) {
  return ORIGIN_LABELS[origin] ?? titleize(origin);
}

/** "18 hours", "3.5 days" — a median that is not a pile of decimals. */
export function formatHours(hours) {
  if (hours === null || hours === undefined) return "—";
  if (hours < 48) return `${Math.round(hours)} ${Math.round(hours) === 1 ? "hour" : "hours"}`;
  const days = Math.round((hours / 24) * 10) / 10;
  return `${days} days`;
}

/**
 * How far written pieces get: to review, to approval, to publication.
 *
 * Every stage is a share of the one before it, which is where a funnel loses
 * people — "approved 40%" means four in ten of the pieces that reached review,
 * not of everything written. The stuck list is the actionable half: pieces
 * sitting in draft or review long enough that nobody is going to get to them
 * by accident.
 */
export function FunnelPanel() {
  const { data, error, loading, reload } = useApi(
    () => api.contentFunnel(DAYS, STALE_DAYS),
    [],
  );

  if (loading && !data) return <Skeleton rows={3} />;
  if (error) return <ErrorBanner message={error} onRetry={reload} />;

  const { overall } = data;
  const steps = [
    { key: "written", label: "Written", value: overall.written, rate: null },
    {
      key: "reached_review",
      label: "Reached review",
      value: overall.reached_review,
      rate: overall.review_rate,
    },
    { key: "approved", label: "Approved", value: overall.approved, rate: overall.approval_rate },
    { key: "published", label: "Published", value: overall.published, rate: overall.publish_rate },
  ];
  const stuck = data.stuck_in_draft + data.stuck_in_review;

  return (
    <section>
      <SectionHeader
        title="From draft to published"
        subtitle={`Pieces written in the last ${data.days} days, and how far each one got.`}
      />

      {overall.written === 0 ? (
        <p className="panel px-5 py-6 text-sm text-ink-500">
          Nothing was written in the last {data.days} days.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Written" value={formatCount(overall.written)} />
            <Stat
              label="Published"
              value={formatRate(overall.overall_rate)}
              hint={`${formatCount(overall.published)} of ${formatCount(overall.written)}`}
            />
            <Stat
              label="Time to publish"
              value={formatHours(data.median_hours_to_publish)}
              hint={data.median_hours_to_publish === null ? "nothing published yet" : "median"}
            />
            <Stat
              label="Stuck"
              value={formatCount(stuck)}
              hint={`idle over ${data.stale_days} days in draft or review`}
            />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-medium text-ink-700">Stages</h3>
              <div className="panel divide-y divide-line">
                {steps.map((step) => (
                  <BarRow
                    key={step.key}
                    label={step.label}
                    value={step.value}
                    max={overall.written}
                    display={formatCount(step.value)}
                    hint={step.rate === null ? null : `${formatRate(step.rate)} of the stage before`}
                  />
                ))}
              </div>
              {overall.dropped > 0 && (
                <p className="mt-2 text-xs text-ink-400">
                  {formatCount(overall.dropped)} archived without being published — rejected in review or withdrawn.
                </p>
              )}
            </div>

            <div>
              <h3 className="mb-2 text-sm font-medium text-ink-700">By where it came from</h3>
              <div className="panel overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-ink-400">
                      <th scope="col" className="px-5 py-2 font-medium">Origin</th>
                      <th scope="col" className="px-3 py-2 text-right font-medium">Written</th>
                      <th scope="col" className="px-3 py-2 text-right font-medium">Published</th>
                      <th scope="col" className="px-5 py-2 text-right font-medium">Rate</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {data.by_origin.map((row) => (
                      <tr key={row.origin}>
                        <th scope="row" className="px-5 py-2 text-left font-normal text-ink-900">
                          {originLabel(row.origin)}
                        </th>
                        <td className="px-3 py-2 text-right font-mono text-xs">{formatCount(row.written)}</td>
                        <td className="px-3 py-2 text-right font-mono text-xs">{formatCount(row.published)}</td>
                        <td className="px-5 py-2 text-right font-mono text-xs">{formatRate(row.overall_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}

      {data.stuck.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-2 text-sm font-medium text-ink-700">
            Stuck for over {data.stale_days} days
          </h3>
          <ul className="panel divide-y divide-line" aria-label="Stuck pieces">
            {data.stuck.map((piece) => (
              <li key={piece.content_id} className="flex items-baseline justify-between gap-4 px-5 py-3">
                <Link to={`/content/${piece.content_id}`} className="min-w-0 truncate text-sm text-brand-500 hover:underline">
                  {piece.title}
                </Link>
                <span className="shrink-0 text-xs text-ink-400">
                  {titleize(piece.status)} · {Math.floor(piece.idle_days)} days · {originLabel(piece.origin)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
