import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import DoAideFooter from "../components/DoAideFooter";
import PublicNav from "../components/PublicNav";
import { useAuth } from "../hooks/useAuth";

/**
 * What an address that is not a route answers with.
 *
 * It used to redirect to /dashboard — which, for anyone signed out, bounced on
 * to the landing page. A mistyped link, an old blog URL or a link from an
 * email for a page Pulse no longer has all arrived somewhere that looked like
 * success and said nothing about what had happened. This says the page is not
 * there, quotes the address so a typo is visible, and offers the one next step
 * that fits who is looking.
 *
 * Not a server 404 — the SPA cannot set a status code — so search engines are
 * told not to index it instead.
 */
export default function NotFound() {
  const { pathname } = useLocation();
  const { user } = useAuth();

  useEffect(() => {
    const previous = document.title;
    document.title = "Page not found · DoAide Pulse";
    const robots = document.createElement("meta");
    robots.name = "robots";
    robots.content = "noindex";
    document.head.appendChild(robots);
    return () => {
      document.title = previous;
      robots.remove();
    };
  }, []);

  return (
    <div className="min-h-screen bg-canvas text-ink-700">
      <PublicNav />

      <main id="main" tabIndex={-1} className="mx-auto max-w-xl px-4 py-20 text-center">
        <p className="eyebrow mb-3 text-brand-500">404</p>
        <h1 className="page-title mb-3">We couldn&rsquo;t find that page</h1>
        <p className="mb-2 text-ink-500">
          Nothing lives at{" "}
          <code className="break-all font-mono text-sm text-ink-700">{pathname}</code>.
        </p>
        <p className="mb-8 text-ink-500">
          The link may be old, or mistyped. Check the address, or carry on from here.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          {user ? (
            <Link to="/dashboard" className="btn-primary">
              Go to your dashboard
            </Link>
          ) : (
            <Link to="/" className="btn-primary">
              Go to the home page
            </Link>
          )}
          <Link to="/blog" className="btn-ghost">
            Read the blog
          </Link>
        </div>
      </main>

      <DoAideFooter />
    </div>
  );
}
