import { useSearchParams } from "react-router-dom";
import { SectionBoundary } from "../components/ErrorBoundary";
import HealthPanel from "../components/seo/HealthPanel";
import SeoPostsPanel from "../components/seo/SeoPostsPanel";
import SitemapsPanel from "../components/seo/SitemapsPanel";

/**
 * SEO across every DoAide site. One page, one panel per job, the open one
 * kept in `?tab=` so a link to "the meta audit" lands on the meta audit.
 */
export const SEO_TABS = [
  { key: "health", label: "Health", Panel: HealthPanel },
  { key: "sitemaps", label: "Sitemaps", Panel: SitemapsPanel },
  { key: "posts", label: "Posts", Panel: SeoPostsPanel },
];

export default function Seo() {
  const [params, setParams] = useSearchParams();
  const active = SEO_TABS.find((t) => t.key === params.get("tab")) || SEO_TABS[0];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="page-title">SEO</h1>
        <p className="mt-1 text-sm text-ink-500">
          Sitemaps, scheduled posts, meta tags and search traffic for every DoAide product.
        </p>
      </div>

      {SEO_TABS.length > 1 && (
        <div className="flex flex-wrap gap-1 border-b border-line" role="tablist" aria-label="SEO">
          {SEO_TABS.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={t.key === active.key}
              onClick={() => setParams({ tab: t.key }, { replace: true })}
              className={`-mb-px min-h-[48px] border-b-2 px-3 text-sm transition-colors ${
                t.key === active.key
                  ? "border-brand-500 font-medium text-ink-900"
                  : "border-transparent text-ink-500 hover:text-ink-900"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      <SectionBoundary name={`seo:${active.key}`}>
        <active.Panel />
      </SectionBoundary>
    </div>
  );
}
