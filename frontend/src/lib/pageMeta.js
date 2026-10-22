import { useEffect } from "react";

export const SITE_ORIGIN = "https://pulse.doaide.com";

/**
 * Point the document's title, description, canonical and social tags at one page.
 *
 * `index.html` ships the homepage's tags, and a single-page app keeps them for
 * every route unless something rewrites them — so before this, every public
 * page declared the homepage as its canonical URL, which tells a crawler the
 * page is a duplicate of `/` and not worth indexing on its own.
 *
 * Tags missing from the document are created rather than skipped, so this
 * works the same in a test DOM as against the shipped `index.html`.
 */
export function applyPageMeta({ title, description, path }) {
  if (typeof document === "undefined") return;
  if (title) {
    document.title = title;
    setMeta("property", "og:title", title);
    setMeta("name", "twitter:title", title);
  }
  if (description) {
    setMeta("name", "description", description);
    setMeta("property", "og:description", description);
    setMeta("name", "twitter:description", description);
  }
  if (path != null) {
    const url = canonicalUrl(path);
    setLink("canonical", url);
    setMeta("property", "og:url", url);
  }
}

/** The absolute canonical URL for an app path, without a trailing slash except at the root. */
export function canonicalUrl(path) {
  const clean = `/${String(path).replace(/^\/+/, "")}`.replace(/(.)\/+$/, "$1");
  return clean === "/" ? `${SITE_ORIGIN}/` : `${SITE_ORIGIN}${clean}`;
}

/** `applyPageMeta` as an effect, re-applied when any of the three change. */
export function usePageMeta({ title, description, path }) {
  useEffect(() => {
    applyPageMeta({ title, description, path });
  }, [title, description, path]);
}

function setMeta(attr, key, content) {
  let el = document.head.querySelector(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function setLink(rel, href) {
  let el = document.head.querySelector(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}
