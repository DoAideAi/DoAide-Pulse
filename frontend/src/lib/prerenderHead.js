/**
 * Rewrite the static head of the built index.html for one route.
 *
 * The client-side `applyPageMeta` fixes the tags once React runs, which is
 * enough for Google. Link unfurlers never run it, so the build also writes
 * `dist/<route>/index.html` with the route's own tags baked in, and the static
 * server's directory-index lookup serves that copy at the route's URL.
 *
 * String surgery rather than a DOM parser: this runs inside the Vite build,
 * against a file we write ourselves, and must not pull a dependency in.
 */
import { canonicalUrl } from "./pageMeta.js";

export function escapeAttr(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function setContent(html, attr, key, value) {
  const tag = new RegExp(`(<meta\\s+${attr}="${key}"\\s+content=")[^"]*(")`);
  return html.replace(tag, (_, open, close) => `${open}${escapeAttr(value)}${close}`);
}

export function withPageMeta(html, { title, description, path, heading }) {
  let out = html;
  // A crawler that does not run JavaScript otherwise finds an empty #root: no
  // h1 and no text. createRoot replaces this the moment React mounts.
  if (heading) {
    const body = description ? `<p>${escapeAttr(description)}</p>` : "";
    out = out.replace(
      '<div id="root"></div>',
      `<div id="root"><main><h1>${escapeAttr(heading)}</h1>${body}</main></div>`,
    );
  }
  if (title) {
    out = out.replace(/<title>[^<]*<\/title>/, `<title>${escapeAttr(title)}</title>`);
    out = setContent(out, "property", "og:title", title);
    out = setContent(out, "name", "twitter:title", title);
  }
  if (description) {
    out = setContent(out, "name", "description", description);
    out = setContent(out, "property", "og:description", description);
    out = setContent(out, "name", "twitter:description", description);
  }
  if (path != null) {
    const url = canonicalUrl(path);
    out = out.replace(
      /(<link\s+rel="canonical"\s+href=")[^"]*(")/,
      (_, open, close) => `${open}${escapeAttr(url)}${close}`,
    );
    out = setContent(out, "property", "og:url", url);
  }
  return out;
}

/** Every route to prerender: the static public pages, then one per blog post. */
export function prerenderRoutes(routeMeta, posts) {
  return [
    ...Object.values(routeMeta)
      .filter((meta) => meta.path !== "/")
      .map((meta) => ({ ...meta, heading: meta.title.replace(/\s*\|\s*DoAide Pulse$/, "") })),
    ...posts.map((post) => ({
      title: `${post.title} | DoAide Pulse`,
      description: post.description,
      path: `/blog/${post.slug}`,
      heading: post.title,
    })),
  ];
}
