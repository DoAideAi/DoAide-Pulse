import { useRef, useState } from "react";
import { Link } from "react-router-dom";

export default function PublicNav() {
  const [toolsOpen, setToolsOpen] = useState(false);
  const toolsButton = useRef(null);
  return (
    <>
      {/* The same skip link the signed-in shell has. Every page that renders
          this nav puts its content in <main id="main">, so a keyboard user
          is one Tab and Enter past the header rather than nine. */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded-md focus:bg-brand-500 focus:px-3 focus:py-1.5 focus:text-sm focus:text-canvas"
      >
        Skip to content
      </a>
      <header className="border-b border-line">
        {/* Wraps rather than overflowing: six links and the wordmark do not fit
            one row at phone width, and an unwrapped row scrolled the whole page
            sideways. */}
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
          <Link to="/" className="flex items-center gap-2 text-base font-semibold text-ink-900">
            DoAide <span className="text-ink-400">|</span> <span className="text-brand-500">Pulse</span>
          </Link>
          <nav aria-label="Public" className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
            {/* A disclosure, not an ARIA menu: these are plain links, and
                role="menu" promised arrow-key handling that was never there.
                It closes when focus leaves the whole group — closing on the
                button's own blur shut it the moment Tab moved into it, so the
                tools could not be reached from the keyboard at all. */}
            <div
              className="relative"
              onBlur={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget)) setToolsOpen(false);
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape" && toolsOpen) {
                  setToolsOpen(false);
                  toolsButton.current?.focus();
                }
              }}
            >
              <button
                ref={toolsButton}
                type="button"
                onClick={() => setToolsOpen(!toolsOpen)}
                aria-expanded={toolsOpen}
                aria-controls="public-nav-tools"
                className="text-ink-500 hover:text-brand-500"
              >
                Free Tools ▾
              </button>
              {toolsOpen && (
                <div
                  id="public-nav-tools"
                  className="absolute right-0 top-full z-10 mt-2 w-56 rounded-lg border border-line bg-paper py-1 shadow-lift"
                >
                  <Link to="/tools/subject-line-tester" className="block px-4 py-2 text-sm text-ink-700 hover:bg-canvas hover:text-brand-500">Subject Line Tester</Link>
                  <Link to="/tools/send-time-optimizer" className="block px-4 py-2 text-sm text-ink-700 hover:bg-canvas hover:text-brand-500">Send Time Optimizer</Link>
                  <Link to="/tools/newsletter-roi-calculator" className="block px-4 py-2 text-sm text-ink-700 hover:bg-canvas hover:text-brand-500">ROI Calculator</Link>
                  <Link to="/tools/content-idea-generator" className="block px-4 py-2 text-sm text-ink-700 hover:bg-canvas hover:text-brand-500">Content Idea Generator</Link>
                </div>
              )}
            </div>
            <Link to="/templates" className="text-ink-500 hover:text-brand-500">Templates</Link>
            <Link to="/gallery" className="text-ink-500 hover:text-brand-500">Gallery</Link>
            <Link to="/blog" className="text-ink-500 hover:text-brand-500">Blog</Link>
            <Link to="/embed" className="text-ink-500 hover:text-brand-500">Embed</Link>
            <Link to="/login" className="btn-primary !py-1.5">Log in</Link>
          </nav>
        </div>
      </header>
    </>
  );
}
