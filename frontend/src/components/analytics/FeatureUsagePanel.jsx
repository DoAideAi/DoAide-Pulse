import { ErrorBanner, SectionHeader, Skeleton } from "../ui/Bits";
import { BarRow } from "../ui/Charts";
import { useApi } from "../../hooks/useApi";
import { api } from "../../lib/api";
import { formatCount } from "../../lib/format";

const DAYS = 30;

/**
 * Which of Pulse's features this account actually uses.
 *
 * Uses are counted from what the browser records (every write and page view)
 * plus autopilot's own pieces, which no click produces. The list of features
 * not used at all is the half worth reading: it is where a feature is either
 * not needed or not found.
 */
export function FeatureUsagePanel() {
  const { data, error, loading, reload } = useApi(() => api.featureUsage(DAYS), []);

  if (loading && !data) return <Skeleton rows={3} />;
  if (error) return <ErrorBanner message={error} onRetry={reload} />;

  const used = data.features.filter((row) => row.uses > 0);
  // `unused` names features by key; the labels are on the rows, every feature
  // having one whether or not it was used.
  const labelOf = Object.fromEntries(data.features.map((row) => [row.feature, row.label]));
  const max = Math.max(...used.map((row) => row.uses), 0);

  return (
    <section>
      <SectionHeader
        title="What gets used"
        subtitle={`Pulse's features by use over the last ${data.days} days.`}
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="panel divide-y divide-line">
          {used.length === 0 ? (
            <p className="px-5 py-6 text-sm text-ink-500">
              Nothing recorded in the last {data.days} days yet.
            </p>
          ) : (
            used.map((row) => (
              <BarRow
                key={row.feature}
                label={row.label}
                value={row.uses}
                max={max}
                display={formatCount(row.uses)}
                hint={`on ${row.active_days} ${row.active_days === 1 ? "day" : "days"}`}
              />
            ))
          )}
        </div>
        <div>
          <h3 className="mb-2 text-sm font-medium text-ink-700">Not used in {data.days} days</h3>
          {data.unused.length === 0 ? (
            <p className="text-sm text-ink-500">Every feature has been used.</p>
          ) : (
            <ul className="flex flex-wrap gap-1.5" aria-label="Features not used">
              {data.unused.map((key) => (
                <li
                  key={key}
                  className="rounded-full border border-line bg-canvas px-2.5 py-1 text-xs text-ink-600"
                >
                  {labelOf[key] ?? key}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
