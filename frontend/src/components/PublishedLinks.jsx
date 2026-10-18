import { Link } from "react-router-dom";
import { Empty, ErrorBanner, SectionHeader, Skeleton } from "./ui/Bits";
import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import { formatWhen, titleize } from "../lib/format";

/**
 * Every published piece and the exact URL it went out at, grouped by project.
 *
 * The counts on the dashboard and the platform tiles said *how many* went out
 * and nowhere said *where* — the only place a live link was visible was the
 * editor, one piece at a time. This lists the links themselves.
 */

/** Pieces grouped by project, each with only its live publications. */
export function groupPublished(items) {
  const groups = new Map();
  for (const item of items ?? []) {
    const live = (item.publications ?? []).filter((p) => p.status === "published");
    if (live.length === 0) continue;
    const key = item.project_name || "Untitled project";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push({ ...item, live });
  }
  return [...groups.entries()].map(([project, pieces]) => ({ project, pieces }));
}

export default function PublishedLinks({ limit = 100, perProject = null, compact = false }) {
  const { data, error, loading, reload } = useApi(
    () => api.listContent({ status: "published", limit }),
    [limit],
  );
  const groups = groupPublished(data);

  return (
    <section>
      <SectionHeader
        title="Published links"
        subtitle="Where each post went live, by project."
        action={
          compact ? (
            <Link to="/publish" className="btn-quiet">
              All links
            </Link>
          ) : null
        }
      />
      <ErrorBanner message={error} onRetry={reload} />
      {loading && !data ? (
        <Skeleton rows={3} />
      ) : groups.length === 0 ? (
        error ? null : (
          <Empty title="Nothing published yet" hint="Published posts and their links appear here." />
        )
      ) : (
        <div className="space-y-4">
          {groups.map(({ project, pieces }) => {
            const shown = perProject ? pieces.slice(0, perProject) : pieces;
            return (
              <div key={project} className="panel">
                <h3 className="border-b border-line px-5 py-3 text-sm font-medium text-ink-900">
                  {project}
                  <span className="ml-2 font-mono text-[11px] text-ink-400">
                    {pieces.length} post{pieces.length === 1 ? "" : "s"}
                  </span>
                </h3>
                <ul className="divide-y divide-line">
                  {shown.map((piece) => (
                    <li key={piece.id} className="px-5 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <Link
                          to={`/content/${piece.id}`}
                          className="min-w-0 truncate text-sm text-ink-900 hover:text-brand-500"
                        >
                          {piece.title}
                        </Link>
                        <span className="shrink-0 font-mono text-[11px] text-ink-400">
                          {formatWhen(piece.published_at ?? piece.live[0]?.published_at)}
                        </span>
                      </div>
                      <ul className="mt-1.5 space-y-1">
                        {piece.live.map((pub) => (
                          <li key={pub.id} className="flex min-w-0 items-center gap-2 text-xs">
                            <span className="chip shrink-0">{titleize(pub.platform)}</span>
                            {pub.external_url ? (
                              <a
                                href={pub.external_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="min-w-0 truncate font-mono text-brand-500 hover:underline"
                              >
                                {pub.external_url}
                              </a>
                            ) : (
                              <span className="text-ink-400">No link returned by the platform</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
                {shown.length < pieces.length && (
                  <Link
                    to="/publish"
                    className="block border-t border-line px-5 py-2 text-center text-xs text-brand-500 hover:text-brand-600"
                  >
                    +{pieces.length - shown.length} more →
                  </Link>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
