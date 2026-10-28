import { useEffect, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import { Skeleton } from "../components/ui/Bits";
import Logo from "../components/ui/Logo";
import PublicNav from "../components/PublicNav";
import DoAideFooter from "../components/DoAideFooter";
import ShareButtons from "../components/ShareButtons";
import SubscribeForm from "../components/SubscribeForm";
import { useApi } from "../hooks/useApi";
import { api } from "../lib/api";
import { formatCount, formatReadLength } from "../lib/format";
import { renderMarkdown } from "../lib/markdown";
import trackEvent from "../lib/trackEvent";
import { applyPageMeta } from "../lib/pageMeta";

export default function PublicArticle() {
  const { slug } = useParams();
  const { data, error, errorStatus, loading, reload } = useApi(
    () => api.publicArticle(slug),
    [slug],
  );
  // Only a 404 means there is no such article. A dropped connection or a 429
  // used to get the same "removed or unpublished" page, which is a dead end
  // for a reader whose link is fine.
  const missing = errorStatus === 404;

  const firedRef = useRef(false);

  useEffect(() => {
    if (data) {
      applyPageMeta({
        title: `${data.title} | DoAide Pulse`,
        description: data.meta_description || data.excerpt,
        path: `/article/${slug}`,
      });
    }
  }, [data]);

  useEffect(() => {
    if (!data) return;
    function onScroll() {
      if (firedRef.current) return;
      const scrolled = window.scrollY + window.innerHeight;
      const threshold = document.body.scrollHeight * 0.75;
      if (scrolled >= threshold) {
        firedRef.current = true;
        trackEvent("read-complete", { slug });
      }
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [data, slug]);

  const origin = typeof window !== "undefined" ? window.location.origin : "https://pulse.doaide.com";
  const articleUrl = `${origin}/article/${slug}`;

  return (
    <div className="min-h-screen bg-canvas text-ink-700">
      <PublicNav />

      <div className="mx-auto max-w-2xl px-4 py-10">
        {loading && (
          <div>
            <p role="status" className="sr-only">Loading article…</p>
            <Skeleton rows={5} />
          </div>
        )}

        {error && !loading && !missing && (
          <div className="panel p-8 text-center" role="alert">
            <p className="text-ink-500">
              {errorStatus === 429
                ? "Too many requests just now. Wait a moment and try again."
                : "The article couldn't be loaded. Check your connection and try again."}
            </p>
            <button type="button" className="btn-primary mt-4" onClick={reload}>
              Try again
            </button>
          </div>
        )}

        {error && !loading && missing && (
          <div className="panel p-8 text-center">
            <p className="text-ink-500">
              This article isn't available — it may have been removed or unpublished.
            </p>
            <Link to="/" className="mt-4 inline-block text-sm text-brand-500 hover:underline">
              Go to DoAide Pulse
            </Link>
          </div>
        )}

        {data && (
          <>
            <article className="stagger">
              {data.cover_image_url && (
                <img
                  src={data.cover_image_url}
                  alt={`Cover image for ${data.title}`}
                  loading="lazy"
                  className="mb-6 aspect-[1200/630] w-full rounded-xl border border-line object-cover"
                />
              )}

              <div className="mb-4 flex flex-wrap items-center gap-2">
                {data.tags.map((tag) => (
                  <span
                    key={tag}
                    className="chip text-brand-500"
                  >
                    {tag}
                  </span>
                ))}
              </div>

              <p className="text-xs text-ink-400 mb-4">
                {data.project_name && <>{data.project_name} · </>}
                {formatCount(data.word_count)} words · {formatReadLength(data.read_minutes)}
                {data.published_at && <> · {new Date(data.published_at).toLocaleDateString()}</>}
              </p>

              <div
                className="prose-pulse panel px-7 py-6"
                dangerouslySetInnerHTML={{
                  __html: `<h1 style="margin-top:0">${escapeText(data.title)}</h1>${renderMarkdown(data.body_markdown)}`,
                }}
              />
            </article>

            <div className="mt-8">
              <SubscribeForm
                source="article"
                heading={
                  data.project_name
                    ? `Get the next ${data.project_name} update by email`
                    : "Get the next one by email"
                }
              />
            </div>

            <div className="panel mt-8 p-6">
              <p className="mb-3 text-sm font-medium text-ink-900">Share this article</p>
              <ShareButtons url={articleUrl} title={data.title} variant="prominent" />
            </div>

            <div className="mt-8 rounded-2xl border border-brand-500/20 bg-brand-50 p-8 text-center">
              <div className="flex items-center justify-center gap-2 mb-3">
                <Logo className="h-5 w-5" />
                <span className="eyebrow text-brand-500">
                  Published with DoAide Pulse
                </span>
              </div>
              <h2 className="font-display text-xl text-ink-900 mb-2">
                Create AI-powered newsletters in minutes
              </h2>
              <p className="text-sm text-ink-500 mb-4">
                Turn your ideas into polished newsletters with AI. Free to start.
              </p>
              <Link
                to="/"
                className="btn-primary"
                onClick={() => trackEvent("cta-click", { source: "article", slug })}
              >
                Try DoAide Pulse for free
              </Link>
            </div>
          </>
        )}
      </div>

      <DoAideFooter />
    </div>
  );
}

function escapeText(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
