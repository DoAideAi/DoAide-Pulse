import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { PUBLIC_ROUTE_META } from "../data/publicRouteMeta";
import { staticPosts } from "../data/blogPosts";
import { escapeAttr, prerenderRoutes, withPageMeta } from "./prerenderHead";

const INDEX = readFileSync(resolve(__dirname, "../../index.html"), "utf-8");
const TOOL = PUBLIC_ROUTE_META["/tools/subject-line-tester"];

describe("withPageMeta against the real index.html", () => {
  const html = withPageMeta(INDEX, TOOL);

  it("replaces the title", () => {
    expect(html).toContain("<title>Subject Line Tester | DoAide Pulse</title>");
    expect(html).not.toContain("<title>DoAide Pulse</title>");
  });

  it("points canonical and og:url at the route", () => {
    const url = "https://pulse.doaide.com/tools/subject-line-tester";
    expect(html).toContain(`<link rel="canonical" href="${url}"`);
    expect(html).toContain(`<meta property="og:url" content="${url}"`);
  });

  it("rewrites every description, including the multi-line one", () => {
    const count = html.split(escapeAttr(TOOL.description)).length - 1;
    expect(count).toBe(3);
  });

  it("rewrites the social titles", () => {
    expect(html).toContain(`<meta property="og:title" content="${TOOL.title}"`);
    expect(html).toContain(`<meta name="twitter:title" content="${TOOL.title}"`);
  });

  it("leaves everything else alone", () => {
    expect(html).toContain('<script type="application/ld+json">');
    expect(html).toContain('<div id="root"></div>');
  });
});

describe("withPageMeta with a heading", () => {
  const html = withPageMeta(INDEX, { ...TOOL, heading: "Subject <Line> Tester" });

  it("gives crawlers an h1 and the description inside #root", () => {
    expect(html).toContain(
      `<div id="root"><main><h1>Subject &lt;Line&gt; Tester</h1><p>${escapeAttr(TOOL.description)}</p></main></div>`,
    );
  });
});

describe("escapeAttr", () => {
  it("cannot be broken out of", () => {
    expect(escapeAttr('a "b" <c> & d')).toBe("a &quot;b&quot; &lt;c&gt; &amp; d");
  });

  it("escapes a quote in a real title before it reaches the head", () => {
    const html = withPageMeta(INDEX, { title: 'Say "hi"', path: "/x" });
    expect(html).toContain("<title>Say &quot;hi&quot;</title>");
  });
});

describe("prerenderRoutes", () => {
  const routes = prerenderRoutes(PUBLIC_ROUTE_META, staticPosts);

  it("skips the homepage, which index.html already is", () => {
    expect(routes.map((r) => r.path)).not.toContain("/");
  });

  it("covers every free tool and every blog post", () => {
    const paths = routes.map((r) => r.path);
    expect(paths).toContain("/tools/send-time-optimizer");
    for (const post of staticPosts) expect(paths).toContain(`/blog/${post.slug}`);
  });

  it("gives every route a title and description", () => {
    for (const r of routes) {
      expect(r.title).toBeTruthy();
      expect(r.description).toBeTruthy();
    }
  });

  it("gives every route an h1 without the site suffix", () => {
    for (const r of routes) {
      expect(r.heading).toBeTruthy();
      expect(r.heading).not.toMatch(/DoAide Pulse$/);
    }
  });
});
