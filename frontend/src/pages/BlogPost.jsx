import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { blogPostIndex } from "../data/blogPostIndex";
import CrossProductLinks from "../components/CrossProductLinks";
import PublicNav from "../components/PublicNav";
import DoAideFooter from "../components/DoAideFooter";
import ShareButtons from "../components/ShareButtons";
import trackEvent from "../lib/trackEvent";
import { loadWithReload } from "../lib/lazyPage";
import { applyPageMeta } from "../lib/pageMeta";

/**
 * One loader per post, so a post view fetches its own body and nobody else's.
 * Importing every post's text (data/blogPosts.js) put about 125 KB of other
 * posts into this page's chunk; the listing fields come from the small index,
 * which is enough to draw the heading and the page's meta straight away.
 */
const CONTENT = import.meta.glob("../data/posts/*.js");

function usePostContent(slug) {
  const [state, setState] = useState({ slug: null, content: null, failed: false });
  const [attempt, setAttempt] = useState(0);
  const load = slug ? CONTENT[`../data/posts/${slug}.js`] : null;

  useEffect(() => {
    if (!load) return undefined;
    let cancelled = false;
    setState({ slug, content: null, failed: false });
    // ``loadWithReload``: after a deploy the chunk this tab knows the name of
    // is gone, and Retry asked for the same missing file forever.
    loadWithReload(load).then(
      (module) => {
        if (!cancelled) setState({ slug, content: module.default, failed: false });
      },
      () => {
        if (!cancelled) setState({ slug, content: null, failed: true });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [load, slug, attempt]);

  // Never another post's text while the next one is on its way.
  const current = state.slug === slug ? state : { content: null, failed: false };
  return { ...current, retry: () => setAttempt((n) => n + 1) };
}

export default function BlogPost() {
  const { slug } = useParams();
  const listed = blogPostIndex.find((p) => p.slug === slug);
  const { content, failed, retry } = usePostContent(listed ? slug : null);
  // A listed slug with no body module is a post that does not exist either.
  const post = listed && CONTENT[`../data/posts/${slug}.js`] ? listed : null;

  useEffect(() => {
    if (post)
      applyPageMeta({
        title: `${post.title} | DoAide Pulse`,
        description: post.description,
        path: `/blog/${post.slug}`,
      });
    else applyPageMeta({ title: "Post not found | DoAide Pulse" });
  }, [post]);

  useEffect(() => {
    if (!post) return;
    const schemas = [
      {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        headline: post.title,
        description: post.description,
        datePublished: post.published,
        keywords: post.keywords.join(", "),
        author: { "@type": "Organization", name: "DoAide Pulse" },
        publisher: {
          "@type": "Organization",
          name: "DoAide Pulse",
          url: "https://pulse.doaide.com",
        },
        mainEntityOfPage: {
          "@type": "WebPage",
          "@id": `https://pulse.doaide.com/blog/${post.slug}`,
        },
      },
      {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Home", item: "https://pulse.doaide.com" },
          { "@type": "ListItem", position: 2, name: "Blog", item: "https://pulse.doaide.com/blog" },
          { "@type": "ListItem", position: 3, name: post.title, item: `https://pulse.doaide.com/blog/${post.slug}` },
        ],
      },
    ];
    const faqs = content?.faqs ?? [];
    if (faqs.length > 0) {
      schemas.push({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        mainEntity: faqs.map((faq) => ({
          "@type": "Question",
          name: faq.question,
          acceptedAnswer: {
            "@type": "Answer",
            text: faq.answer,
          },
        })),
      });
    }
    const script = document.createElement("script");
    script.type = "application/ld+json";
    script.textContent = JSON.stringify(schemas);
    document.head.appendChild(script);
    return () => {
      document.head.removeChild(script);
    };
  }, [post, content]);

  if (!post) {
    return (
      <div className="min-h-screen bg-canvas text-ink-700">
        <PublicNav />
        <main id="main" tabIndex={-1} className="mx-auto max-w-2xl px-4 py-10">
          <p className="text-ink-500">
            Post not found.{" "}
            <Link to="/blog" className="text-brand-500 hover:underline">
              Back to blog
            </Link>
          </p>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-canvas text-ink-700">
      <PublicNav />
      <main id="main" tabIndex={-1}>
        <article className="mx-auto max-w-2xl px-4 py-10">
          <nav aria-label="Breadcrumb" className="mb-6 font-mono text-[11px] text-ink-400">
            <Link to="/" className="hover:text-brand-500">Home</Link>
            <span className="mx-2" aria-hidden="true">/</span>
            <Link to="/blog" className="hover:text-brand-500">Blog</Link>
            <span className="mx-2" aria-hidden="true">/</span>
            <span className="text-ink-500" aria-current="page">{post.title}</span>
          </nav>

          <div className="flex flex-wrap gap-2 mb-4">
            {post.keywords.map((kw) => (
              <span key={kw} className="chip text-brand-500">
                {kw}
              </span>
            ))}
          </div>

          <h1 className="font-display text-3xl md:text-4xl text-ink-900 mb-2 leading-tight">{post.title}</h1>
          <time className="text-xs text-ink-400">{post.published}</time>

          <div className="mt-8 space-y-5" aria-busy={!content && !failed}>
            {content &&
              content.body.map((para, i) => (
                <p key={i} className="text-[15px] leading-[1.8] text-ink-700">{para}</p>
              ))}
            {!content && !failed && (
              <div className="space-y-3" aria-label="Loading the post">
                {[0, 1, 2, 3].map((i) => (
                  <div key={i} className="h-4 animate-pulse rounded bg-ink-50" />
                ))}
              </div>
            )}
            {failed && (
              // Most often a tab opened before a deploy, asking for a chunk the
              // new build no longer has.
              <p className="text-sm text-ink-500" role="alert">
                This post could not load.{" "}
                <button type="button" className="text-brand-500 hover:underline" onClick={retry}>
                  Try again
                </button>{" "}
                or reload the page.
              </p>
            )}
          </div>

          {content?.faqs && content.faqs.length > 0 && (
            <section className="mt-10">
              <h2 className="text-xl font-display text-ink-900 mb-4">Frequently Asked Questions</h2>
              <dl className="space-y-4">
                {content.faqs.map((faq, i) => (
                  <div key={i} className="panel p-4">
                    <dt className="text-[15px] font-medium text-ink-900 mb-2">{faq.question}</dt>
                    <dd className="text-[14px] leading-[1.7] text-ink-700">{faq.answer}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          <div className="panel mt-12 p-6 text-center">
            <p className="mb-3 text-ink-900 font-medium">
              Build newsletters that convert — powered by AI.
            </p>
            <Link to="/" className="btn-primary" onClick={() => trackEvent("cta-click", { source: "blog-post", slug })}>
              Try DoAide Pulse
            </Link>
          </div>

          <div className="mt-6">
            <ShareButtons text={`${post.title} — read on DoAide Pulse`} />
          </div>
          <CrossProductLinks page="blog" />
        </article>
      </main>
      <DoAideFooter />
    </div>
  );
}
