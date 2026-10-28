import { ErrorBanner, SectionHeader, Skeleton, Stat } from "../ui/Bits";
import { BarRow } from "../ui/Charts";
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";
import { formatCount, formatRate, titleize } from "../../lib/format";

const DAYS = 90;

/** Why autopilot held a piece for review, in the words a reviewer would use. */
const HOLD_REASON_LABELS = {
  not_eligible: "Not a candidate (review-only mode or low confidence)",
  dead_links: "Dead links",
  seo_score: "SEO score below the bar",
  seo_errors: "SEO errors",
  garbled: "Garbled text",
  unsupported_names: "Names the sources do not support",
  duplicate: "Repeats an earlier piece",
  quality: "Quality score below the floor",
};

export function holdReasonLabel(reason) {
  return HOLD_REASON_LABELS[reason] ?? titleize(reason);
}

/**
 * How well autopilot's gates judge: what it approved on its own, what it held
 * and why, and how often a person disagreed afterwards — in both directions.
 * A held piece published anyway says the gates are too strict; an
 * auto-approved piece pulled before it went out says they are too lenient.
 */
export function AutopilotPanel() {
  const { data, error, loading, reload } = useApi(() => api.autopilotEffectiveness(DAYS), []);

  if (loading && !data) return <Skeleton rows={3} />;
  if (error) return <ErrorBanner message={error} onRetry={reload} />;

  if (data.routed === 0) {
    return (
      <section>
        <SectionHeader title="How autopilot judges" />
        <p className="panel px-5 py-6 text-sm text-ink-500">
          Autopilot has not written anything in the last {data.days} days.
        </p>
      </section>
    );
  }

  const maxReason = Math.max(...data.hold_reasons.map((row) => row.count), 0);

  return (
    <section>
      <SectionHeader
        title="How autopilot judges"
        subtitle={`What it approved on its own in the last ${data.days} days, what it held, and how often people disagreed.`}
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Approved on its own"
          value={formatRate(data.auto_rate)}
          hint={`${formatCount(data.auto_approved)} of ${formatCount(data.routed)} written`}
        />
        <Stat
          label="Held, then published"
          value={formatRate(data.override_rate)}
          hint={`${formatCount(data.held_published)} of ${formatCount(data.held)} held — gates too strict?`}
        />
        <Stat
          label="Held, then archived"
          value={formatRate(data.rejection_rate)}
          hint={`${formatCount(data.held_rejected)} of ${formatCount(data.held)} held — the gates were right`}
        />
        <Stat
          label="Approved, then pulled"
          value={formatRate(data.pulled_rate)}
          hint={`${formatCount(data.auto_pulled)} of ${formatCount(data.auto_approved)} approved — gates too lenient?`}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-medium text-ink-700">Why pieces were held</h3>
          <div className="panel divide-y divide-line">
            {data.hold_reasons.length === 0 ? (
              <p className="px-5 py-6 text-sm text-ink-500">Nothing was held.</p>
            ) : (
              data.hold_reasons.map((row) => (
                <BarRow
                  key={row.reason}
                  label={holdReasonLabel(row.reason)}
                  value={row.count}
                  max={maxReason}
                  display={formatCount(row.count)}
                />
              ))
            )}
          </div>
          <p className="mt-2 text-xs text-ink-400">
            A piece can be held for more than one reason.
          </p>
        </div>

        <div>
          <h3 className="mb-2 text-sm font-medium text-ink-700">Quality score</h3>
          <div className="panel overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-ink-400">
                  <th scope="col" className="px-5 py-2 font-medium">Score</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Approved</th>
                  <th scope="col" className="px-5 py-2 text-right font-medium">Held</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.quality_distribution.map((row) => (
                  <tr key={row.bucket}>
                    <th scope="row" className="px-5 py-2 text-left font-mono text-xs font-normal text-ink-900">
                      {row.bucket}
                    </th>
                    <td className="px-3 py-2 text-right font-mono text-xs">{formatCount(row.auto)}</td>
                    <td className="px-5 py-2 text-right font-mono text-xs">{formatCount(row.held)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-ink-400">
            Median {data.median_quality_auto ?? "—"} approved, {data.median_quality_held ?? "—"} held.
          </p>
        </div>
      </div>

      {(data.auto_below_seo_threshold > 0 || data.inferred > 0) && (
        <ul className="mt-4 space-y-1 text-xs text-ink-400">
          {data.auto_below_seo_threshold > 0 && (
            <li>
              {formatCount(data.auto_below_seo_threshold)} approved below the SEO bar, because the
              model was confident enough to waive it.
            </li>
          )}
          {data.inferred > 0 && (
            <li>
              {formatCount(data.inferred)} of these {formatCount(data.routed)} were written before
              autopilot recorded its decisions, so theirs is inferred from their gate results.
            </li>
          )}
        </ul>
      )}
    </section>
  );
}
